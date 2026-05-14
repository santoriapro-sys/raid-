'use strict';
require('dotenv').config();

const {
  Client, GatewayIntentBits, Partials,
  EmbedBuilder, ActionRowBuilder, ButtonBuilder,
  ButtonStyle, StringSelectMenuBuilder, PermissionFlagsBits,
  ChannelType
} = require('discord.js');

// ═══════════════════════════════════════════════════════════
//  CONFIG
// ═══════════════════════════════════════════════════════════
const CONFIG = {
  token:         process.env.TOKEN,
  ownerId:       process.env.OWNER_ID || '1191963306785787946',
  mainGuildId:   process.env.MAIN_GUILD_ID || '',
  supportInvite: process.env.SUPPORT_INVITE || 'https://discord.gg/2PvXETvFFG',
  prefix:        process.env.PREFIX || '+',
  color:         0x2B2D31
};

// ═══════════════════════════════════════════════════════════
//  BASE DE DONNÉES (JSON en mémoire + fichier)
// ═══════════════════════════════════════════════════════════
const fs   = require('fs');
const path = require('path');

const DATA_DIR = path.join(process.cwd(), 'data');
const DB_FILE  = path.join(DATA_DIR, 'db.json');

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
if (!fs.existsSync(DB_FILE))  fs.writeFileSync(DB_FILE, '{}', 'utf8');

const DB = {
  read() {
    try { return JSON.parse(fs.readFileSync(DB_FILE, 'utf8')); } catch { return {}; }
  },
  write(data) {
    fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf8');
  },
  get(key, def = null) {
    const d = this.read();
    return d[key] !== undefined ? d[key] : def;
  },
  set(key, val) {
    const d = this.read();
    d[key] = val;
    this.write(d);
  },
  del(key) {
    const d = this.read();
    delete d[key];
    this.write(d);
  },

  getPoints(id)           { return this.get(`pts_${id}`, 0); },
  addPoints(id, n)        { this.set(`pts_${id}`, this.getPoints(id) + n); },
  removePoints(id, n)     { this.set(`pts_${id}`, Math.max(0, this.getPoints(id) - n)); },
  setPoints(id, n)        { this.set(`pts_${id}`, n); },

  getInvites(id)          { return this.get(`inv_${id}`, 0); },
  addInvites(id, n)       { this.set(`inv_${id}`, this.getInvites(id) + n); },

  getGens(id)             { return this.get(`gen_${id}`, 0); },
  incGens(id)             { this.set(`gen_${id}`, this.getGens(id) + 1); },

  resetUser(id)           { this.del(`pts_${id}`); this.del(`inv_${id}`); this.del(`gen_${id}`); },

  getCooldown(id, cmd)    { return this.get(`cd_${cmd}_${id}`, null); },
  setCooldown(id, cmd, t) { this.set(`cd_${cmd}_${id}`, t); }
};

// ═══════════════════════════════════════════════════════════
//  SESSIONS QUESTIONNAIRE
// ═══════════════════════════════════════════════════════════
const sessions = new Map();

const STEPS = [
  { key: 'serverName',  q: 'Quel est le **nom** de votre serveur ?',              type: 'text' },
  { key: 'theme',       q: 'Quel est le **thème** principal ?',                    type: 'text' },
  { key: 'members',     q: 'Combien de **membres** prévus ?',                      type: 'text' },
  { key: 'language',    q: 'Quelle est la **langue** principale ?',                type: 'text' },
  { key: 'rolesCount',  q: 'Combien de **rôles** souhaitez-vous ? (3-10)',         type: 'text' },
  { key: 'style',       q: 'Quel est le **style** de votre serveur ?',             type: 'select_style' },
  { key: 'features',    q: 'Quelles **fonctionnalités** souhaitez-vous ?',         type: 'select_features' },
  { key: 'finish',      q: 'Quel **niveau de finition** souhaitez-vous ?',         type: 'select_finish' },
  { key: 'colors',      q: 'Quelles sont les **couleurs dominantes** ?',           type: 'text' },
  { key: 'founder',     q: 'Quel est le **nom du fondateur** ?',                   type: 'text' }
];

// ═══════════════════════════════════════════════════════════
//  EMBEDS
// ═══════════════════════════════════════════════════════════
function embedBase(title, desc, color = CONFIG.color) {
  return new EmbedBuilder()
    .setColor(color)
    .setTitle(title)
    .setDescription(desc)
    .setFooter({ text: 'Generate  •  Système de génération de serveur' })
    .setTimestamp();
}

function embedOk(title, desc)   { return embedBase(title, desc, 0x57F287); }
function embedErr(title, desc)  { return embedBase(title, desc, 0xED4245); }
function embedWarn(title, desc) { return embedBase(title, desc, 0xFEE75C); }

function progressBar(step, total) {
  const f = Math.round((step / total) * 10);
  return '`' + '█'.repeat(f) + '░'.repeat(10 - f) + '`' + ` ${Math.round((step / total) * 100)}%`;
}

function embedQuestion(step, total, stepObj) {
  return new EmbedBuilder()
    .setColor(CONFIG.color)
    .setTitle(`◈  Configuration  —  Étape ${step}/${total}`)
    .setDescription(`${progressBar(step, total)}\n\n**${stepObj.q}**`)
    .setFooter({ text: `Generate  •  Étape ${step} sur ${total}` })
    .setTimestamp();
}

function embedPanel(client) {
  return new EmbedBuilder()
    .setColor(CONFIG.color)
    .setTitle('◈  Generate')
    .setDescription(
      '```\nGénère un serveur Discord complet et personnalisé.\n```\n' +
      '**Catégories  •  Salons  •  Rôles  •  Règles  •  Bienvenue**\n\n' +
      '─────────────────────────────\n' +
      '**〔 Accès 〕**\n' +
      `> Rejoins : [discord.gg/2PvXETvFFG](${CONFIG.supportInvite})\n` +
      '> `1 invitation = 1 crédit = 1 génération`\n\n' +
      '─────────────────────────────\n' +
      '**〔 Utilisation 〕**\n' +
      '> `+generate` → Questions en DM → Serveur construit automatiquement'
    )
    .setThumbnail(client.user.displayAvatarURL({ size: 256 }))
    .setFooter({ text: 'Generate  •  Serveur professionnel en quelques minutes' })
    .setTimestamp();
}

function embedSummary(data) {
  const features = Array.isArray(data.features) ? data.features.join(', ') : data.features;
  return new EmbedBuilder()
    .setColor(CONFIG.color)
    .setTitle('◈  Récapitulatif')
    .setDescription(
      `> **Nom :** ${data.serverName}\n` +
      `> **Thème :** ${data.theme}\n` +
      `> **Membres :** ${data.members}\n` +
      `> **Langue :** ${data.language}\n` +
      `> **Rôles :** ${data.rolesCount}\n` +
      `> **Style :** ${data.style}\n` +
      `> **Finition :** ${data.finish}\n` +
      `> **Couleurs :** ${data.colors}\n` +
      `> **Fondateur :** ${data.founder}\n` +
      `> **Options :** ${features}\n\n` +
      '─────────────────────────────\n' +
      '> Confirme pour lancer la génération.'
    )
    .setFooter({ text: 'Generate  •  Confirme pour continuer' })
    .setTimestamp();
}

// ─── Composants ────────────────────────────────────────────
function rowPanelButtons() {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder().setLabel('Support').setEmoji('🔗').setStyle(ButtonStyle.Link).setURL(CONFIG.supportInvite),
    new ButtonBuilder().setCustomId('btn_start').setLabel('Générer un serveur').setEmoji('⚡').setStyle(ButtonStyle.Secondary)
  );
}

function rowConfirm() {
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('btn_confirm').setLabel('Confirmer').setEmoji('✅').setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId('btn_cancel').setLabel('Annuler').setEmoji('✖').setStyle(ButtonStyle.Danger)
  );
}

function rowStyle() {
  return new ActionRowBuilder().addComponents(
    new StringSelectMenuBuilder().setCustomId('sel_style').setPlaceholder('Choisissez un style...').addOptions([
      { label: 'Gaming',      value: 'gaming',     emoji: '🎮' },
      { label: 'Communauté',  value: 'communaute', emoji: '💬' },
      { label: 'E-girl',      value: 'egirl',      emoji: '🌸' },
      { label: 'Business',    value: 'business',   emoji: '💼' },
      { label: 'Chill',       value: 'chill',      emoji: '🌙' },
      { label: 'Anime',       value: 'anime',      emoji: '⛩️' },
      { label: 'Stream',      value: 'stream',     emoji: '📺' },
      { label: 'Autre',       value: 'autre',      emoji: '✨' }
    ])
  );
}

function rowFeatures() {
  return new ActionRowBuilder().addComponents(
    new StringSelectMenuBuilder().setCustomId('sel_features').setPlaceholder('Fonctionnalités...').setMinValues(1).setMaxValues(10).addOptions([
      { label: 'Salons vocaux',      value: 'voice',         emoji: '🔊' },
      { label: 'Système ticket',     value: 'tickets',       emoji: '🎫' },
      { label: 'Logs',               value: 'logs',          emoji: '📋' },
      { label: 'Règlement',          value: 'rules',         emoji: '📜' },
      { label: 'Annonces',           value: 'announcements', emoji: '📢' },
      { label: 'Présentation',       value: 'presentation',  emoji: '👤' },
      { label: 'Staff',              value: 'staff',         emoji: '🛡️' },
      { label: 'Boosters',           value: 'boosters',      emoji: '💎' },
      { label: 'Giveaways',          value: 'giveaways',     emoji: '🎁' },
      { label: 'Rôles colorés',      value: 'colored_roles', emoji: '🎨' }
    ])
  );
}

function rowFinish() {
  return new ActionRowBuilder().addComponents(
    new StringSelectMenuBuilder().setCustomId('sel_finish').setPlaceholder('Niveau de finition...').addOptions([
      { label: 'Simple',       value: 'simple', emoji: '⚪', description: 'Essentiel uniquement' },
      { label: 'Avancé',       value: 'avance', emoji: '🔵', description: 'Configuration complète' },
      { label: 'Ultra Premium',value: 'ultra',  emoji: '🟣', description: 'Setup complet premium' }
    ])
  );
}

function getRowForStep(step) {
  if (step.type === 'select_style')    return [rowStyle()];
  if (step.type === 'select_features') return [rowFeatures()];
  if (step.type === 'select_finish')   return [rowFinish()];
  return [];
}

// ═══════════════════════════════════════════════════════════
//  SERVER BUILDER
// ═══════════════════════════════════════════════════════════
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

const STYLE_EMOJIS = {
  gaming:     { g: '🎮', v: '🎮', n: '🏆' },
  communaute: { g: '💬', v: '🔊', n: '📢' },
  egirl:      { g: '🌸', v: '🎀', n: '💌' },
  business:   { g: '💼', v: '📞', n: '📊' },
  chill:      { g: '🌙', v: '🎵', n: '🌟' },
  anime:      { g: '⛩️', v: '🎌', n: '📯' },
  stream:     { g: '📺', v: '🎙️', n: '📡' },
  autre:      { g: '💬', v: '🔊', n: '📢' }
};

async function buildServer(guild, data) {
  const stats    = { categories: 0, channels: 0, roles: 0 };
  const em       = STYLE_EMOJIS[data.style] || STYLE_EMOJIS.autre;
  const features = Array.isArray(data.features) ? data.features : [data.features];
  const isAdv    = data.finish === 'avance' || data.finish === 'ultra';
  const isUltra  = data.finish === 'ultra';
  const everyoneId = guild.roles.everyone.id;

  // 1. Nettoyage
  for (const ch of guild.channels.cache.values()) { try { await ch.delete(); } catch {} await sleep(300); }
  for (const r  of guild.roles.cache.values())    { if (r.id === guild.id || r.managed) continue; try { await r.delete(); } catch {} await sleep(300); }

  // 2. Rôles
const useColors = features.includes('colored_roles');

  const roleDefs = [
    { key: 'admin',   name: '『👑』Administration', color: useColors ? 0xFF6B6B : 0x000000, hoist: true,  perms: [PermissionFlagsBits.Administrator] },
    { key: 'mod',     name: '『🛡️』Modérateur',     color: useColors ? 0x4ECDC4 : 0x000000, hoist: true,  perms: [PermissionFlagsBits.ManageMessages, PermissionFlagsBits.KickMembers] },
    { key: 'member',  name: '『👤』Membre',          color: 0x000000,                         hoist: false, perms: [] },
    { key: 'newbie',  name: '『🌱』Nouveau',         color: 0x000000,                         hoist: false, perms: [] }
  ];

  if (features.includes('staff'))     roleDefs.splice(2, 0, { key: 'staff',   name: '『⚔️』Staff',    color: useColors ? 0xA8E6CF : 0x000000, hoist: true,  perms: [PermissionFlagsBits.ManageMessages] });
  if (features.includes('boosters'))  roleDefs.push(        { key: 'booster', name: '『💎』Booster',  color: useColors ? 0xF8B500 : 0x000000, hoist: false, perms: [] });
  if (features.includes('giveaways')) roleDefs.push(        { key: 'giveaway',name: '『🎁』Giveaway', color: useColors ? 0xFF69B4 : 0x000000, hoist: false, perms: [] });

  const roles = {};
  for (const def of roleDefs) {
    roles[def.key] = await guild.roles.create({
      name: def.name,
      color: def.color,
      hoist: def.hoist,
      permissions: def.perms,
      reason: 'Generate'
    });
    stats.roles++;
    await sleep(400);
  }

  // ─── Helper créer salon texte ───────────────────────────
  async function makeTxt(name, parent, canSend = true, viewRoleId = everyoneId) {
    await guild.channels.create({
      name,
      type: ChannelType.GuildText,
      parent: parent?.id,
      permissionOverwrites: [{
        id: viewRoleId,
        allow: [PermissionFlagsBits.ViewChannel, ...(canSend ? [PermissionFlagsBits.SendMessages] : [])],
        deny:  canSend ? [] : [PermissionFlagsBits.SendMessages]
      }],
      reason: 'Generate'
    });
    stats.channels++;
    await sleep(400);
  }

  async function makeCat(name, hidden = false, allowRoleId = null) {
    const overw = hidden
      ? [{ id: everyoneId, deny: [PermissionFlagsBits.ViewChannel] },
         ...(allowRoleId ? [{ id: allowRoleId, allow: [PermissionFlagsBits.ViewChannel] }] : [])]
      : [];
    const cat = await guild.channels.create({ name, type: ChannelType.GuildCategory, permissionOverwrites: overw, reason: 'Generate' });
    stats.categories++;
    await sleep(300);
    return cat;
  }

  // 3. Catégories & salons
  // ─── INFO ──────────────────────────────────────────────
  if (features.includes('announcements') || features.includes('rules') || features.includes('presentation')) {
    const cat = await makeCat('─── ◈ Information ───');
    if (features.includes('announcements')) await makeTxt(`『📢』annonces`,     cat, false);
    if (features.includes('rules'))         await makeTxt(`『📜』règlement`,    cat, false);
    if (features.includes('presentation'))  await makeTxt(`『👤』présentations`,cat, true);
    if (isAdv)                              await makeTxt(`『📅』événements`,   cat, false);
  }

  // ─── GÉNÉRAL ───────────────────────────────────────────
  const catGen = await makeCat('─── ◈ Général ───');
  await makeTxt(`『${em.g}』général`,   catGen, true);
  await makeTxt(`『💬』off-topic`,       catGen, true);
  if (isAdv) {
    await makeTxt(`『😂』memes`,  catGen, true);
    await makeTxt(`『📸』médias`, catGen, true);
  }

  // ─── VOCAL ─────────────────────────────────────────────
  if (features.includes('voice')) {
    const catV = await makeCat('─── ◈ Vocal ───');
    const count = Math.min(Math.max(parseInt(data.rolesCount) || 3, 1), 5);
    for (let i = 1; i <= count; i++) {
      await guild.channels.create({ name: `『${em.v}』vocal-${i}`, type: ChannelType.GuildVoice, parent: catV.id, reason: 'Generate' });
      stats.channels++; await sleep(400);
    }
    if (isAdv) {
      await guild.channels.create({ name: `『🎙️』lounge`, type: ChannelType.GuildVoice, parent: catV.id, userLimit: 10, reason: 'Generate' });
      stats.channels++; await sleep(400);
    }
  }

  // ─── TICKETS ───────────────────────────────────────────
  if (features.includes('tickets')) {
    const catT = await makeCat('─── ◈ Support ───');
    await makeTxt(`『🎫』ouvrir-un-ticket`, catT, false);
    if (isAdv) await makeTxt(`『📋』tickets-en-cours`, catT, false, roles.admin?.id || everyoneId);
  }

  // ─── LOGS ──────────────────────────────────────────────
  if (features.includes('logs') && isAdv) {
    const catL = await makeCat('─── ◈ Logs ───', true, roles.admin?.id);
    await makeTxt(`『📋』logs-membres`,     catL, false, roles.admin?.id || everyoneId);
    await makeTxt(`『🔨』logs-modération`,  catL, false, roles.admin?.id || everyoneId);
    if (isUltra) await makeTxt(`『⚙️』logs-serveur`, catL, false, roles.admin?.id || everyoneId);
  }

  // ─── STAFF ─────────────────────────────────────────────
  if (features.includes('staff') && isAdv) {
    const catS = await makeCat('─── ◈ Staff ───', true, roles.admin?.id);
    await makeTxt(`『👑』staff-général`, catS, true, roles.admin?.id || everyoneId);
    await makeTxt(`『📝』réunions`,      catS, true, roles.admin?.id || everyoneId);
  }

  // ─── BOOSTERS ──────────────────────────────────────────
  if (features.includes('boosters') && isUltra && roles.booster) {
    const catB = await makeCat('─── ◈ Boosters ───', true, roles.booster.id);
    await makeTxt(`『💎』salon-boosters`, catB, true, roles.booster.id);
  }

  // ─── GIVEAWAYS ─────────────────────────────────────────
  if (features.includes('giveaways') && isAdv) {
    const catG = await makeCat('─── ◈ Giveaways ───');
    await makeTxt(`『🎁』giveaways`, catG, false);
    await makeTxt(`『🏆』gagnants`,  catG, false);
  }

  return stats;
}

// ═══════════════════════════════════════════════════════════
//  CLIENT
// ═══════════════════════════════════════════════════════════
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildInvites,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.DirectMessages
  ],
  partials: [Partials.Channel, Partials.Message, Partials.User]
});

// ═══════════════════════════════════════════════════════════
//  READY
// ═══════════════════════════════════════════════════════════
client.once('ready', () => {
  console.log(`✅ ${client.user.tag} est en ligne !`);
  client.user.setPresence({ activities: [{ name: '+help | Generate', type: 0 }], status: 'dnd' });
});

// ═══════════════════════════════════════════════════════════
//  MESSAGE CREATE
// ═══════════════════════════════════════════════════════════
client.on('messageCreate', async (message) => {
  if (message.author.bot) return;

  // ─── DM : réponse questionnaire ──────────────────────────
  if (!message.guild) {
    const session = sessions.get(message.author.id);
    if (!session) return;
    const step = STEPS[session.step];
    if (!step || step.type !== 'text') return;

    session.data[step.key] = message.content.trim();
    session.step++;

    if (session.step >= STEPS.length) {
      return message.reply({ embeds: [embedSummary(session.data)], components: [rowConfirm()] });
    }

    const nextStep = STEPS[session.step];
    const embed    = embedQuestion(session.step + 1, STEPS.length, nextStep);
    return message.reply({ embeds: [embed], components: getRowForStep(nextStep) });
  }

  // ─── Commandes ────────────────────────────────────────────
  if (!message.content.startsWith(CONFIG.prefix)) return;
  const args = message.content.slice(CONFIG.prefix.length).trim().split(/ +/);
  const cmd  = args.shift().toLowerCase();

  // ── +help ─────────────────────────────────────────────────
  if (cmd === 'help') {
    return message.channel.send({ embeds: [embedPanel(client)], components: [rowPanelButtons()] });
  }

  // ── +points ───────────────────────────────────────────────
  if (cmd === 'points') {
    const pts  = DB.getPoints(message.author.id);
    const gens = DB.getGens(message.author.id);
    return message.reply({ embeds: [embedBase('◈  Vos crédits',
      `> 🪙 **Crédits :** \`${pts}\`\n> ⚡ **Générations :** \`${gens}\`\n\n> *1 invitation = 1 crédit*`
    )] });
  }

  // ── +invites ──────────────────────────────────────────────
  if (cmd === 'invites') {
    const inv = DB.getInvites(message.author.id);
    const pts = DB.getPoints(message.author.id);
    return message.reply({ embeds: [embedBase('◈  Vos invitations',
      `> 🔗 **Invitations :** \`${inv}\`\n> 🪙 **Crédits :** \`${pts}\`\n\n> Invite sur [le serveur officiel](${CONFIG.supportInvite})`
    )] });
  }

  // ── +generate ─────────────────────────────────────────────
  if (cmd === 'generate') {
    if (sessions.has(message.author.id))
      return message.reply({ embeds: [embedWarn('Session active', '> Tu as déjà un questionnaire en cours dans tes DMs.')] });

    if (message.author.id !== CONFIG.ownerId) {
      const pts = DB.getPoints(message.author.id);
      if (pts < 1)
        return message.reply({ embeds: [embedErr('Crédits insuffisants',
          `> Tu n'as pas de crédits.\n> **Crédits :** \`${pts}\`\n> Invite des membres pour en obtenir.`
        )] });
    }

    const cd = DB.getCooldown(message.author.id, 'generate');
    if (cd && Date.now() - cd < 30000 && message.author.id !== CONFIG.ownerId) {
      const left = Math.ceil((30000 - (Date.now() - cd)) / 1000);
      return message.reply({ embeds: [embedWarn('Cooldown', `> Attends encore **${left}s**.`)] });
    }

    sessions.set(message.author.id, { step: 0, data: {}, guildId: message.guild.id });
    DB.setCooldown(message.author.id, 'generate', Date.now());

    const firstStep = STEPS[0];
    const embed     = embedQuestion(1, STEPS.length, firstStep);

    try {
      await message.author.send({ embeds: [embed], components: getRowForStep(firstStep) });
      return message.reply({ embeds: [embedOk('Questionnaire envoyé', '> Réponds aux questions dans tes **DMs** !')] });
    } catch {
      sessions.delete(message.author.id);
      return message.reply({ embeds: [embedErr('DMs fermés', '> Active tes messages privés et réessaie.')] });
    }
  }

  // ── OWNER : +addpoints ────────────────────────────────────
  if (cmd === 'addpoints' && message.author.id === CONFIG.ownerId) {
    const user   = message.mentions.users.first();
    const amount = parseInt(args[1]);
    if (!user || isNaN(amount)) return message.reply({ embeds: [embedWarn('Usage', '> `+addpoints @user nombre`')] });
    DB.addPoints(user.id, amount);
    return message.reply({ embeds: [embedOk('Crédits ajoutés', `> ✅ **+${amount}** crédits → ${user}\n> **Total :** \`${DB.getPoints(user.id)}\``)] });
  }

  // ── OWNER : +removepoints ─────────────────────────────────
  if (cmd === 'removepoints' && message.author.id === CONFIG.ownerId) {
    const user   = message.mentions.users.first();
    const amount = parseInt(args[1]);
    if (!user || isNaN(amount)) return message.reply({ embeds: [embedWarn('Usage', '> `+removepoints @user nombre`')] });
    DB.removePoints(user.id, amount);
    return message.reply({ embeds: [embedOk('Crédits retirés', `> ✅ **-${amount}** crédits → ${user}\n> **Total :** \`${DB.getPoints(user.id)}\``)] });
  }

  // ── OWNER : +resetuser ────────────────────────────────────
  if (cmd === 'resetuser' && message.author.id === CONFIG.ownerId) {
    const user = message.mentions.users.first();
    if (!user) return message.reply({ embeds: [embedWarn('Usage', '> `+resetuser @user`')] });
    DB.resetUser(user.id);
    return message.reply({ embeds: [embedOk('Reset effectué', `> ✅ ${user} a été réinitialisé.`)] });
  }

  // ── OWNER : +forcegenerate ────────────────────────────────
  if (cmd === 'forcegenerate' && message.author.id === CONFIG.ownerId) {
    const user = message.mentions.users.first();
    if (!user) return message.reply({ embeds: [embedWarn('Usage', '> `+forcegenerate @user`')] });
    DB.addPoints(user.id, 1);
    return message.reply({ embeds: [embedOk('Génération forcée', `> ✅ 1 crédit ajouté à ${user}.`)] });
  }
});

// ═══════════════════════════════════════════════════════════
//  INTERACTION CREATE
// ═══════════════════════════════════════════════════════════
client.on('interactionCreate', async (interaction) => {

  // ─── Bouton : Générer un serveur (panel) ──────────────────
  if (interaction.isButton() && interaction.customId === 'btn_start') {
    if (sessions.has(interaction.user.id))
      return interaction.reply({ embeds: [embedWarn('Session active', '> Tu as déjà un questionnaire en cours dans tes DMs.')], ephemeral: true });

    if (interaction.user.id !== CONFIG.ownerId) {
      const pts = DB.getPoints(interaction.user.id);
      if (pts < 1)
        return interaction.reply({ embeds: [embedErr('Crédits insuffisants', `> Tu n'as pas de crédits.\n> Invite des membres sur le serveur officiel.`)], ephemeral: true });
    }

    sessions.set(interaction.user.id, { step: 0, data: {}, guildId: interaction.guild?.id });

    const firstStep = STEPS[0];
    const embed     = embedQuestion(1, STEPS.length, firstStep);

    try {
      await interaction.user.send({ embeds: [embed], components: getRowForStep(firstStep) });
      return interaction.reply({ embeds: [embedOk('Questionnaire envoyé', '> Réponds aux questions dans tes **DMs** !')], ephemeral: true });
    } catch {
      sessions.delete(interaction.user.id);
      return interaction.reply({ embeds: [embedErr('DMs fermés', '> Active tes messages privés.')], ephemeral: true });
    }
  }

  // ─── Select menus (dans DMs) ──────────────────────────────
  if (interaction.isStringSelectMenu()) {
    const session = sessions.get(interaction.user.id);
    if (!session) return interaction.reply({ content: 'Session expirée.', ephemeral: true });

    const step  = STEPS[session.step];
    const value = interaction.values.length === 1 ? interaction.values[0] : interaction.values;
    session.data[step.key] = value;
    session.step++;

    await interaction.update({ components: [] });

    if (session.step >= STEPS.length) {
      return interaction.followUp({ embeds: [embedSummary(session.data)], components: [rowConfirm()] });
    }

    const nextStep = STEPS[session.step];
    return interaction.followUp({ embeds: [embedQuestion(session.step + 1, STEPS.length, nextStep)], components: getRowForStep(nextStep) });
  }

  // ─── Bouton : Confirmer génération ───────────────────────
  if (interaction.isButton() && interaction.customId === 'btn_confirm') {
    const session = sessions.get(interaction.user.id);
    if (!session) return interaction.update({ embeds: [embedErr('Session expirée', '> Relance `+generate`.')], components: [] });

    const guild = client.guilds.cache.get(session.guildId);
    if (!guild) {
      sessions.delete(interaction.user.id);
      return interaction.update({ embeds: [embedErr('Serveur introuvable', '> Impossible de trouver ton serveur.')], components: [] });
    }

    if (!guild.members.me?.permissions.has(PermissionFlagsBits.Administrator)) {
      sessions.delete(interaction.user.id);
      return interaction.update({ embeds: [embedErr('Permissions manquantes', '> Le bot doit être **Administrateur** sur ton serveur.')], components: [] });
    }

    await interaction.update({
      embeds: [embedBase('◈  Génération en cours...', '`▓▓▓▓▓░░░░░` — Construction...\n\n*Patiente quelques secondes.*')],
      components: []
    });

    try {
      const stats = await buildServer(guild, session.data);

      if (interaction.user.id !== CONFIG.ownerId) DB.removePoints(interaction.user.id, 1);
      DB.incGens(interaction.user.id);
      sessions.delete(interaction.user.id);

      return interaction.editReply({
        embeds: [embedOk('◈  Génération terminée ✓',
          `**${session.data.serverName}** est prêt !\n\n` +
          `> 📂 **Catégories :** ${stats.categories}\n` +
          `> 💬 **Salons :** ${stats.channels}\n` +
          `> 🎭 **Rôles :** ${stats.roles}`
        )]
      });
    } catch (err) {
      sessions.delete(interaction.user.id);
      return interaction.editReply({ embeds: [embedErr('Erreur', `> \`${err.message}\``)] });
    }
  }

  // ─── Bouton : Annuler ─────────────────────────────────────
  if (interaction.isButton() && interaction.customId === 'btn_cancel') {
    sessions.delete(interaction.user.id);
    return interaction.update({ embeds: [embedWarn('Annulé', '> La génération a été annulée.')], components: [] });
  }
});

// ═══════════════════════════════════════════════════════════
//  ANTI-CRASH
// ═══════════════════════════════════════════════════════════
process.on('unhandledRejection', err => console.error('Rejection:', err));
process.on('uncaughtException',  err => console.error('Exception:', err));

// ═══════════════════════════════════════════════════════════
//  LOGIN
// ═══════════════════════════════════════════════════════════
if (!CONFIG.token) {
  console.error('❌ TOKEN manquant dans les variables Railway');
  process.exit(1);
}

client.login(CONFIG.token)
  .then(() => console.log('✅ Generate connecté !'))
  .catch(err => { console.error('❌ Login failed:', err.message); process.exit(1); });
