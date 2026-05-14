'use strict';
require('dotenv').config();

const {
  Client, GatewayIntentBits, Partials,
  EmbedBuilder, ActionRowBuilder, ButtonBuilder,
  ButtonStyle, StringSelectMenuBuilder, PermissionFlagsBits,
  ChannelType, AuditLogEvent
} = require('discord.js');
const fs   = require('fs');
const path = require('path');
const axios = require('axios');

// ═══════════════════════════════════════════════════════════
//  CONFIG
// ═══════════════════════════════════════════════════════════
const CONFIG = {
  token:          process.env.TOKEN,
  ownerId:        process.env.OWNER_ID || '1191963306785787946',
  supportInvite:  process.env.SUPPORT_INVITE || 'https://discord.gg/2PvXETvFFG',
  prefix:         process.env.PREFIX || '+',
  color:          0x2B2D31,
  anthropicKey:   process.env.ANTHROPIC_API_KEY || ''
};

// ═══════════════════════════════════════════════════════════
//  DATABASE
// ═══════════════════════════════════════════════════════════
const DATA_DIR = path.join(process.cwd(), 'data');
const DB_FILE  = path.join(DATA_DIR, 'db.json');

if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
if (!fs.existsSync(DB_FILE))  fs.writeFileSync(DB_FILE, '{}', 'utf8');

const DB = {
  read()        { try { return JSON.parse(fs.readFileSync(DB_FILE, 'utf8')); } catch { return {}; } },
  write(data)   { fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf8'); },
  get(k, d=null){ const db=this.read(); return db[k]!==undefined?db[k]:d; },
  set(k,v)      { const db=this.read(); db[k]=v; this.write(db); },
  del(k)        { const db=this.read(); delete db[k]; this.write(db); },

  getPoints(id)         { return this.get(`pts_${id}`, 0); },
  addPoints(id,n)       { this.set(`pts_${id}`, this.getPoints(id)+n); },
  removePoints(id,n)    { this.set(`pts_${id}`, Math.max(0,this.getPoints(id)-n)); },
  getGens(id)           { return this.get(`gen_${id}`, 0); },
  incGens(id)           { this.set(`gen_${id}`, this.getGens(id)+1); },
  resetUser(id)         { this.del(`pts_${id}`); this.del(`gen_${id}`); },
  getCooldown(id,cmd)   { return this.get(`cd_${cmd}_${id}`, null); },
  setCooldown(id,cmd,t) { this.set(`cd_${cmd}_${id}`, t); },

  // Ticket system
  getTicketConfig(guildId)    { return this.get(`tkt_config_${guildId}`, null); },
  setTicketConfig(guildId, v) { this.set(`tkt_config_${guildId}`, v); },
  getTicket(channelId)        { return this.get(`tkt_${channelId}`, null); },
  setTicket(channelId, v)     { this.set(`tkt_${channelId}`, v); },
  delTicket(channelId)        { this.del(`tkt_${channelId}`); },
  getTicketCount(guildId)     { return this.get(`tkt_count_${guildId}`, 0); },
  incTicketCount(guildId)     { const n=this.getTicketCount(guildId)+1; this.set(`tkt_count_${guildId}`,n); return n; },

  // Logs config
  getLogsConfig(guildId)    { return this.get(`logs_${guildId}`, null); },
  setLogsConfig(guildId, v) { this.set(`logs_${guildId}`, v); }
};

// ═══════════════════════════════════════════════════════════
//  SESSIONS
// ═══════════════════════════════════════════════════════════
const sessions = new Map();

const STEPS = [
  { key: 'serverName', q: 'Quel est le **nom** de votre serveur ?',            type: 'text' },
  { key: 'theme',      q: 'Quel est le **thème / domaine** principal ?',        type: 'text' },
  { key: 'members',    q: 'Combien de **membres** prévus ?',                    type: 'text' },
  { key: 'language',   q: 'Quelle est la **langue** principale ?',              type: 'text' },
  { key: 'rolesCount', q: 'Combien de **rôles** souhaitez-vous ? (3-10)',       type: 'text' },
  { key: 'style',      q: 'Quel est le **style** de votre serveur ?',           type: 'select_style' },
  { key: 'features',   q: 'Quelles **fonctionnalités** souhaitez-vous ?',       type: 'select_features' },
  { key: 'finish',     q: 'Quel **niveau de finition** souhaitez-vous ?',       type: 'select_finish' },
  { key: 'colors',     q: 'Quelles sont les **couleurs / ambiance** ?',         type: 'text' },
  { key: 'founder',    q: 'Quel est le **nom du fondateur** ?',                 type: 'text' }
];

// ═══════════════════════════════════════════════════════════
//  CLAUDE API — génération unique du plan serveur
// ═══════════════════════════════════════════════════════════
async function generateServerPlan(data) {
  if (!CONFIG.anthropicKey) return null;

  const features = Array.isArray(data.features) ? data.features.join(', ') : data.features;
  const prompt = `Tu es un expert en création de serveurs Discord. Génère un plan de serveur Discord UNIQUE et CRÉATIF basé sur ces informations :

- Nom : ${data.serverName}
- Thème : ${data.theme}
- Membres prévus : ${data.members}
- Langue : ${data.language}
- Rôles souhaités : ${data.rolesCount}
- Style : ${data.style}
- Fonctionnalités : ${features}
- Finition : ${data.finish}
- Couleurs/Ambiance : ${data.colors}
- Fondateur : ${data.founder}

Réponds UNIQUEMENT en JSON valide avec cette structure :
{
  "welcomeMessage": "message de bienvenue personnalisé et accrocheur (2-3 phrases)",
  "rulesText": "règlement adapté au thème (5 règles numérotées)",
  "categoryNames": ["nom catégorie 1", "nom catégorie 2", ...],
  "channelTopics": {
    "general": "topic du salon général adapté au thème",
    "off-topic": "topic off-topic fun",
    "announcements": "topic annonces"
  },
  "customRoles": ["Rôle 1 thématique", "Rôle 2 thématique"],
  "serverDescription": "description courte du serveur (1 phrase)",
  "welcomeEmbed": {
    "title": "titre embed de bienvenue",
    "description": "description embed de bienvenue avec infos utiles"
  }
}`;

  try {
    const res = await axios.post('https://api.anthropic.com/v1/messages', {
      model: 'claude-opus-4-20250514',
      max_tokens: 1200,
      messages: [{ role: 'user', content: prompt }]
    }, {
      headers: {
        'x-api-key': CONFIG.anthropicKey,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
      },
      timeout: 30000
    });

    const text = res.data.content[0].text;
    const json = text.replace(/```json\n?/g,'').replace(/```\n?/g,'').trim();
    return JSON.parse(json);
  } catch(e) {
    console.error('Claude API error:', e.message);
    return null;
  }
}

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
  const clientId = client.user.id;
  const botInvite = `https://discord.com/oauth2/authorize?client_id=${clientId}&permissions=8&scope=bot%20applications.commands`;

  return new EmbedBuilder()
    .setColor(CONFIG.color)
    .setTitle('◈  Generate')
    .setDescription(
      '```\nGénère un serveur Discord complet et personnalisé.\n```\n' +
      '**Catégories  •  Salons  •  Rôles  •  Tickets  •  Logs  •  Règlement**\n\n' +
      '─────────────────────────────\n' +
      '**〔 Comment ça marche 〕**\n' +
      '> 1. Ajoute le bot sur ton serveur via le bouton ci-dessous\n' +
      '> 2. Lance `+generate` ici pour configurer\n' +
      '> 3. Choisis le serveur cible\n' +
      '> 4. Réponds aux questions → ton serveur est généré !'
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

function embedGuildSelect(guilds) {
  const list = guilds.map((g,i) => `> \`${i+1}.\` **${g.name}** — ${g.memberCount} membres`).join('\n');
  return new EmbedBuilder()
    .setColor(CONFIG.color)
    .setTitle('◈  Choisir le serveur cible')
    .setDescription(
      '**Sur quel serveur veux-tu générer la structure ?**\n\n' +
      list + '\n\n' +
      '─────────────────────────────\n' +
      '> ⚠️ **Attention :** Tous les salons et rôles existants seront **supprimés et remplacés**.'
    )
    .setFooter({ text: 'Generate  •  Sélectionne un serveur' })
    .setTimestamp();
}

// ─── Composants ────────────────────────────────────────────
function rowPanelButtons(clientId) {
  const botInvite = `https://discord.com/oauth2/authorize?client_id=${clientId}&permissions=8&scope=bot%20applications.commands`;
  return new ActionRowBuilder().addComponents(
    new ButtonBuilder().setLabel('Ajouter le bot').setEmoji('🤖').setStyle(ButtonStyle.Link).setURL(botInvite),
    new ButtonBuilder().setCustomId('btn_start').setLabel('Générer un serveur').setEmoji('⚡').setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setLabel('Support').setEmoji('🔗').setStyle(ButtonStyle.Link).setURL(CONFIG.supportInvite)
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
      { label: 'Simple',        value: 'simple', emoji: '⚪', description: 'Essentiel uniquement' },
      { label: 'Avancé',        value: 'avance', emoji: '🔵', description: 'Configuration complète' },
      { label: 'Ultra Premium', value: 'ultra',  emoji: '🟣', description: 'Setup complet premium' }
    ])
  );
}

function getRowForStep(step) {
  if (step.type === 'select_style')    return [rowStyle()];
  if (step.type === 'select_features') return [rowFeatures()];
  if (step.type === 'select_finish')   return [rowFinish()];
  return [];
}

function rowGuildSelect(guilds) {
  return new ActionRowBuilder().addComponents(
    new StringSelectMenuBuilder()
      .setCustomId('sel_guild')
      .setPlaceholder('Choisir un serveur...')
      .addOptions(
        guilds.slice(0, 25).map(g => ({
          label: g.name.slice(0, 100),
          value: g.id,
          description: `${g.memberCount} membres`
        }))
      )
  );
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

async function buildServer(guild, data, plan) {
  const stats    = { categories: 0, channels: 0, roles: 0, configured: 0 };
  const em       = STYLE_EMOJIS[data.style] || STYLE_EMOJIS.autre;
  const features = Array.isArray(data.features) ? data.features : [data.features];
  const isAdv    = data.finish === 'avance' || data.finish === 'ultra';
  const isUltra  = data.finish === 'ultra';
  const everyoneId = guild.roles.everyone.id;
  const channelRefs = {};

  // 1. Nettoyage
  for (const ch of guild.channels.cache.values()) { try { await ch.delete(); } catch {} await sleep(250); }
  for (const r  of guild.roles.cache.values())    { if (r.id === guild.id || r.managed) continue; try { await r.delete(); } catch {} await sleep(250); }

  // 2. Rôles
  const useColors = features.includes('colored_roles');

  const roleDefs = [
    { key: 'admin',   name: '『👑』Administration', color: useColors ? 0xFF6B6B : 0x000000, hoist: true,  perms: [PermissionFlagsBits.Administrator] },
    { key: 'mod',     name: '『🛡️』Modérateur',    color: useColors ? 0x4ECDC4 : 0x000000, hoist: true,  perms: [PermissionFlagsBits.ManageMessages, PermissionFlagsBits.KickMembers, PermissionFlagsBits.BanMembers] },
    { key: 'member',  name: '『👤』Membre',          color: 0x000000,                         hoist: false, perms: [] },
    { key: 'newbie',  name: '『🌱』Nouveau',         color: 0x000000,                         hoist: false, perms: [] }
  ];

  // Rôles custom générés par l'IA
  if (plan?.customRoles?.length) {
    for (const rName of plan.customRoles.slice(0, 3)) {
      roleDefs.splice(2, 0, { key: `custom_${rName}`, name: rName, color: 0x000000, hoist: false, perms: [] });
    }
  }

  if (features.includes('staff'))     roleDefs.splice(2, 0, { key: 'staff',   name: '『⚔️』Staff',    color: useColors ? 0xA8E6CF : 0x000000, hoist: true,  perms: [PermissionFlagsBits.ManageMessages] });
  if (features.includes('boosters'))  roleDefs.push(        { key: 'booster', name: '『💎』Booster',  color: useColors ? 0xF8B500 : 0x000000, hoist: false, perms: [] });
  if (features.includes('giveaways')) roleDefs.push(        { key: 'giveaway',name: '『🎁』Giveaway', color: useColors ? 0xFF69B4 : 0x000000, hoist: false, perms: [] });

  const roles = {};
  for (const def of roleDefs) {
    roles[def.key] = await guild.roles.create({
      name: def.name, color: def.color, hoist: def.hoist,
      permissions: def.perms, reason: 'Generate'
    });
    stats.roles++;
    await sleep(350);
  }

  // ─── Helpers ───────────────────────────────────────────
  async function makeCat(name, hidden = false, allowRoleId = null) {
    const overw = hidden
      ? [{ id: everyoneId, deny: [PermissionFlagsBits.ViewChannel] },
         ...(allowRoleId ? [{ id: allowRoleId, allow: [PermissionFlagsBits.ViewChannel] }] : [])]
      : [];
    const cat = await guild.channels.create({ name, type: ChannelType.GuildCategory, permissionOverwrites: overw, reason: 'Generate' });
    stats.categories++;
    await sleep(250);
    return cat;
  }

  async function makeTxt(name, parent, opts = {}) {
    const {
      canSend    = true,
      viewRoleId = everyoneId,
      topic      = null,
      slowmode   = 0,
      nsfw       = false,
      readOnly   = false
    } = opts;

    const ch = await guild.channels.create({
      name,
      type: ChannelType.GuildText,
      parent: parent?.id,
      topic: topic || undefined,
      rateLimitPerUser: slowmode,
      nsfw,
      permissionOverwrites: [{
        id: viewRoleId,
        allow: [PermissionFlagsBits.ViewChannel, ...(canSend && !readOnly ? [PermissionFlagsBits.SendMessages] : [])],
        deny:  readOnly ? [PermissionFlagsBits.SendMessages] : []
      }],
      reason: 'Generate'
    });
    stats.channels++;
    await sleep(350);
    return ch;
  }

  async function makeVoice(name, parent, limit = 0) {
    await guild.channels.create({
      name, type: ChannelType.GuildVoice, parent: parent?.id,
      userLimit: limit, reason: 'Generate'
    });
    stats.channels++;
    await sleep(350);
  }

  // 3. CATÉGORIES & SALONS

  // ─── INFO ──────────────────────────────────────────────
  if (features.includes('announcements') || features.includes('rules') || features.includes('presentation')) {
    const cat = await makeCat('─── ◈ Information ───');
    if (features.includes('announcements')) {
      const ch = await makeTxt(`『📢』annonces`, cat, {
        canSend: false, readOnly: true,
        topic: plan?.channelTopics?.announcements || 'Retrouvez toutes les annonces officielles ici.'
      });
      channelRefs.announcements = ch;
    }
    if (features.includes('rules')) {
      const ch = await makeTxt(`『📜』règlement`, cat, {
        canSend: false, readOnly: true,
        topic: 'Lisez et respectez le règlement du serveur.'
      });
      channelRefs.rules = ch;
    }
    if (features.includes('presentation')) {
      await makeTxt(`『👤』présentations`, cat, {
        topic: 'Présente-toi à la communauté !', slowmode: 300
      });
    }
    if (isAdv) {
      await makeTxt(`『📅』événements`, cat, {
        canSend: false, readOnly: true,
        topic: 'Tous les événements à venir.'
      });
    }
  }

  // ─── GÉNÉRAL ───────────────────────────────────────────
  const catGen = await makeCat('─── ◈ Général ───');
  const genCh = await makeTxt(`『${em.g}』général`, catGen, {
    topic: plan?.channelTopics?.general || `Bienvenue sur ${data.serverName} ! Parlez de tout ici.`,
    slowmode: 3
  });
  channelRefs.general = genCh;

  await makeTxt(`『💬』off-topic`, catGen, {
    topic: plan?.channelTopics?.['off-topic'] || 'Discussions hors-sujet, détente !',
    slowmode: 5
  });

  if (isAdv) {
    await makeTxt(`『😂』memes`, catGen, { topic: 'Partagez vos meilleurs memes !', slowmode: 10 });
    await makeTxt(`『📸』médias`, catGen, { topic: 'Photos, vidéos, créations...', slowmode: 15 });
  }
  if (isUltra) {
    await makeTxt(`『🎨』créations`, catGen, { topic: 'Partagez vos créations artistiques.', slowmode: 30 });
  }

  // ─── BIENVENUE ─────────────────────────────────────────
  if (isAdv) {
    const catW = await makeCat('─── ◈ Bienvenue ───');
    const welcomeCh = await makeTxt(`『👋』bienvenue`, catW, { canSend: false, readOnly: true,
      topic: `Bienvenue sur ${data.serverName} !` });
    channelRefs.welcome = welcomeCh;
    await makeTxt(`『🎭』choix-rôles`, catW, { topic: 'Sélectionnez vos rôles ici.', readOnly: false });
  }

  // ─── VOCAL ─────────────────────────────────────────────
  if (features.includes('voice')) {
    const catV = await makeCat('─── ◈ Vocal ───');
    const count = Math.min(Math.max(parseInt(data.rolesCount) || 3, 1), 5);
    for (let i = 1; i <= count; i++) {
      await makeVoice(`『${em.v}』Vocal ${i}`, catV);
    }
    if (isAdv) {
      await makeVoice(`『🎙️』Lounge`, catV, 10);
      await makeVoice(`『🎵』Musique`, catV, 20);
    }
    if (isUltra) {
      await makeVoice(`『📞』Privé 1`, catV, 5);
      await makeVoice(`『📞』Privé 2`, catV, 5);
    }
  }

  // ─── TICKETS ───────────────────────────────────────────
  if (features.includes('tickets')) {
    const catT = await makeCat('─── ◈ Support ───');
    const ticketPanel = await makeTxt(`『🎫』ouvrir-un-ticket`, catT, {
      readOnly: true, topic: 'Cliquez sur le bouton ci-dessous pour ouvrir un ticket.'
    });
    channelRefs.ticketPanel = ticketPanel;

    if (isAdv) {
      const ticketLog = await makeTxt(`『📋』historique-tickets`, catT, {
        readOnly: true,
        viewRoleId: roles.mod?.id || everyoneId
      });
      channelRefs.ticketLog = ticketLog;
    }

    // Sauvegarder config tickets
    DB.setTicketConfig(guild.id, {
      panelChannelId: ticketPanel.id,
      logChannelId:   channelRefs.ticketLog?.id || null,
      modRoleId:      roles.mod?.id || null,
      adminRoleId:    roles.admin?.id || null
    });
  }

  // ─── LOGS ──────────────────────────────────────────────
  if (features.includes('logs')) {
    const catL = await makeCat('─── ◈ Logs ───', true, roles.admin?.id);

    const logJoin  = await makeTxt(`『✅』logs-arrivées`,    catL, { readOnly: true, viewRoleId: roles.admin?.id || everyoneId });
    const logLeave = await makeTxt(`『❌』logs-départs`,     catL, { readOnly: true, viewRoleId: roles.admin?.id || everyoneId });
    const logMod   = await makeTxt(`『🔨』logs-modération`,  catL, { readOnly: true, viewRoleId: roles.admin?.id || everyoneId });
    const logMsg   = isAdv ? await makeTxt(`『💬』logs-messages`, catL, { readOnly: true, viewRoleId: roles.admin?.id || everyoneId }) : null;
    const logSrv   = isUltra ? await makeTxt(`『⚙️』logs-serveur`, catL, { readOnly: true, viewRoleId: roles.admin?.id || everyoneId }) : null;

    DB.setLogsConfig(guild.id, {
      joinChannelId:  logJoin.id,
      leaveChannelId: logLeave.id,
      modChannelId:   logMod.id,
      msgChannelId:   logMsg?.id  || null,
      srvChannelId:   logSrv?.id  || null
    });
  }

  // ─── STAFF ─────────────────────────────────────────────
  if (features.includes('staff')) {
    // Catégorie cachée à tout le monde sauf staff/admin
    const catS = await guild.channels.create({
      name: '─── ◈ Staff ───',
      type: ChannelType.GuildCategory,
      permissionOverwrites: [
        { id: everyoneId, deny: [PermissionFlagsBits.ViewChannel] },
        ...(roles.staff  ? [{ id: roles.staff.id,  allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages] }] : []),
        ...(roles.admin  ? [{ id: roles.admin.id,  allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages] }] : []),
        ...(roles.mod    ? [{ id: roles.mod.id,    allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages] }] : [])
      ],
      reason: 'Generate'
    });
    stats.categories++;
    await sleep(250);

    // Salons staff — héritent des perms de la catégorie
    await guild.channels.create({ name: `『👑』staff-général`, type: ChannelType.GuildText, parent: catS.id, topic: 'Discussions internes au staff.', reason: 'Generate' });
    stats.channels++; await sleep(350);
    await guild.channels.create({ name: `『📝』réunions`, type: ChannelType.GuildText, parent: catS.id, topic: 'Comptes-rendus de réunions.', reason: 'Generate' });
    stats.channels++; await sleep(350);
    await guild.channels.create({ name: `『📋』sanctions`, type: ChannelType.GuildText, parent: catS.id, topic: 'Suivi des sanctions membres.', reason: 'Generate' });
    stats.channels++; await sleep(350);
    if (isAdv) {
      await guild.channels.create({ name: `『🔔』alertes`, type: ChannelType.GuildText, parent: catS.id, topic: 'Alertes internes.', reason: 'Generate' });
      stats.channels++; await sleep(350);
    }
    if (isUltra) {
      await guild.channels.create({ name: `『⚙️』config-bot`, type: ChannelType.GuildText, parent: catS.id, topic: 'Configuration des bots du serveur.', reason: 'Generate' });
      stats.channels++; await sleep(350);
    }
  }

  // ─── BOOSTERS ──────────────────────────────────────────
  if (features.includes('boosters') && isUltra && roles.booster) {
    const catB = await makeCat('─── ◈ Boosters ───', true, roles.booster.id);
    await makeTxt(`『💎』salon-boosters`, catB, { viewRoleId: roles.booster.id, topic: 'Salon exclusif pour les boosters !' });
  }

  // ─── GIVEAWAYS ─────────────────────────────────────────
  if (features.includes('giveaways') && isAdv) {
    const catG = await makeCat('─── ◈ Giveaways ───');
    await makeTxt(`『🎁』giveaways`, catG, { readOnly: true, topic: 'Participe aux giveaways !' });
    await makeTxt(`『🏆』gagnants`,  catG, { readOnly: true, topic: 'Félicitations aux gagnants !' });
  }

  // 4. POST-SETUP : envoyer les messages dans les salons configurés

  // ─── Règlement ─────────────────────────────────────────
  if (channelRefs.rules && plan?.rulesText) {
    try {
      const rulesEmbed = new EmbedBuilder()
        .setColor(CONFIG.color)
        .setTitle(`📜  Règlement — ${data.serverName}`)
        .setDescription(plan.rulesText)
        .setFooter({ text: `${data.serverName}  •  Tout le monde doit respecter ces règles` })
        .setTimestamp();
      await channelRefs.rules.send({ embeds: [rulesEmbed] });
      stats.configured++;
    } catch(e) { console.error('Rules msg error:', e.message); }
  }

  // ─── Bienvenue ─────────────────────────────────────────
  if (channelRefs.welcome) {
    try {
      const wEmbed = new EmbedBuilder()
        .setColor(CONFIG.color)
        .setTitle(plan?.welcomeEmbed?.title || `👋  Bienvenue sur ${data.serverName} !`)
        .setDescription(plan?.welcomeEmbed?.description || plan?.welcomeMessage || `Bienvenue ! Prends le temps de lire le règlement.`)
        .addFields(
          { name: '📜 Règlement', value: channelRefs.rules ? `<#${channelRefs.rules.id}>` : 'Lis le règlement !', inline: true },
          { name: '💬 Général',   value: channelRefs.general ? `<#${channelRefs.general.id}>` : 'Rejoins la discussion !', inline: true }
        )
        .setFooter({ text: `${data.serverName}  •  Fondé par ${data.founder}` })
        .setTimestamp();
      await channelRefs.welcome.send({ embeds: [wEmbed] });
      stats.configured++;
    } catch(e) { console.error('Welcome msg error:', e.message); }
  }

  // ─── Ticket Panel ──────────────────────────────────────
  if (channelRefs.ticketPanel) {
    try {
      const tEmbed = new EmbedBuilder()
        .setColor(CONFIG.color)
        .setTitle('🎫  Système de Tickets')
        .setDescription(
          '> Besoin d\'aide ou d\'assistance ?\n' +
          '> Clique sur le bouton ci-dessous pour **ouvrir un ticket** privé.\n\n' +
          '```\n📋 Un membre du staff vous répondra rapidement.\n```'
        )
        .setFooter({ text: `${data.serverName}  •  Support` })
        .setTimestamp();

      const tRow = new ActionRowBuilder().addComponents(
        new ButtonBuilder()
          .setCustomId('ticket_open')
          .setLabel('Ouvrir un ticket')
          .setEmoji('🎫')
          .setStyle(ButtonStyle.Secondary)
      );
      await channelRefs.ticketPanel.send({ embeds: [tEmbed], components: [tRow] });
      stats.configured++;
    } catch(e) { console.error('Ticket panel error:', e.message); }
  }

  // ─── Général : message de lancement ────────────────────
  if (channelRefs.general) {
    try {
      const launchEmbed = new EmbedBuilder()
        .setColor(CONFIG.color)
        .setTitle(`🚀  ${data.serverName} est maintenant en ligne !`)
        .setDescription(plan?.serverDescription || `Bienvenue sur **${data.serverName}** — le serveur est prêt, profitez-en !`)
        .setFooter({ text: `Generate  •  Serveur généré` })
        .setTimestamp();
      await channelRefs.general.send({ embeds: [launchEmbed] });
      stats.configured++;
    } catch(e) { console.error('Launch msg error:', e.message); }
  }

  return { stats, channelRefs, roles };
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
    GatewayIntentBits.DirectMessages,
    GatewayIntentBits.GuildModeration
  ],
  partials: [Partials.Channel, Partials.Message, Partials.User, Partials.GuildMember]
});

// ═══════════════════════════════════════════════════════════
//  READY
// ═══════════════════════════════════════════════════════════
client.once('ready', () => {
  console.log(`✅ ${client.user.tag} est en ligne !`);
  client.user.setPresence({ activities: [{ name: '+help | Generate by IA', type: 0 }], status: 'dnd' });
});

// ═══════════════════════════════════════════════════════════
//  LOGS — Membres
// ═══════════════════════════════════════════════════════════
client.on('guildMemberAdd', async (member) => {
  const logsConfig = DB.getLogsConfig(member.guild.id);
  if (!logsConfig?.joinChannelId) return;
  try {
    const ch = await member.guild.channels.fetch(logsConfig.joinChannelId).catch(() => null);
    if (!ch) return;
    const embed = new EmbedBuilder()
      .setColor(0x57F287)
      .setTitle('✅  Nouveau membre')
      .setThumbnail(member.user.displayAvatarURL({ size: 128 }))
      .setDescription(`> ${member} — **${member.user.tag}**`)
      .addFields(
        { name: 'Compte créé', value: `<t:${Math.floor(member.user.createdTimestamp/1000)}:R>`, inline: true },
        { name: 'Membres',     value: `\`${member.guild.memberCount}\``, inline: true }
      )
      .setFooter({ text: `ID : ${member.id}` })
      .setTimestamp();
    await ch.send({ embeds: [embed] });
  } catch(e) { console.error('Log join error:', e.message); }
});

client.on('guildMemberRemove', async (member) => {
  const logsConfig = DB.getLogsConfig(member.guild.id);
  if (!logsConfig?.leaveChannelId) return;
  try {
    const ch = await member.guild.channels.fetch(logsConfig.leaveChannelId).catch(() => null);
    if (!ch) return;
    const embed = new EmbedBuilder()
      .setColor(0xED4245)
      .setTitle('❌  Membre parti')
      .setThumbnail(member.user.displayAvatarURL({ size: 128 }))
      .setDescription(`> **${member.user.tag}**`)
      .addFields(
        { name: 'Rejoint le', value: member.joinedAt ? `<t:${Math.floor(member.joinedTimestamp/1000)}:R>` : 'Inconnu', inline: true },
        { name: 'Membres',    value: `\`${member.guild.memberCount}\``, inline: true }
      )
      .setFooter({ text: `ID : ${member.id}` })
      .setTimestamp();
    await ch.send({ embeds: [embed] });
  } catch(e) { console.error('Log leave error:', e.message); }
});

// ═══════════════════════════════════════════════════════════
//  LOGS — Messages supprimés
// ═══════════════════════════════════════════════════════════
client.on('messageDelete', async (message) => {
  if (!message.guild || message.author?.bot) return;
  const logsConfig = DB.getLogsConfig(message.guild.id);
  if (!logsConfig?.msgChannelId) return;
  try {
    const ch = await message.guild.channels.fetch(logsConfig.msgChannelId).catch(() => null);
    if (!ch) return;
    const embed = new EmbedBuilder()
      .setColor(0xFEE75C)
      .setTitle('💬  Message supprimé')
      .setDescription(
        `> **Auteur :** ${message.author || 'Inconnu'}\n` +
        `> **Salon :** ${message.channel}\n` +
        `> **Contenu :** ${(message.content || '*Message sans texte*').slice(0, 1000)}`
      )
      .setFooter({ text: `ID message : ${message.id}` })
      .setTimestamp();
    await ch.send({ embeds: [embed] });
  } catch(e) { console.error('Log msg delete error:', e.message); }
});

// ═══════════════════════════════════════════════════════════
//  LOGS — Bans / Unbans
// ═══════════════════════════════════════════════════════════
client.on('guildBanAdd', async (ban) => {
  const logsConfig = DB.getLogsConfig(ban.guild.id);
  if (!logsConfig?.modChannelId) return;
  try {
    const ch = await ban.guild.channels.fetch(logsConfig.modChannelId).catch(() => null);
    if (!ch) return;
    const embed = new EmbedBuilder()
      .setColor(0xED4245)
      .setTitle('🔨  Membre banni')
      .setDescription(`> **Utilisateur :** ${ban.user.tag}\n> **Raison :** ${ban.reason || 'Aucune raison'}`)
      .setFooter({ text: `ID : ${ban.user.id}` })
      .setTimestamp();
    await ch.send({ embeds: [embed] });
  } catch(e) { console.error('Log ban error:', e.message); }
});

client.on('guildBanRemove', async (ban) => {
  const logsConfig = DB.getLogsConfig(ban.guild.id);
  if (!logsConfig?.modChannelId) return;
  try {
    const ch = await ban.guild.channels.fetch(logsConfig.modChannelId).catch(() => null);
    if (!ch) return;
    const embed = new EmbedBuilder()
      .setColor(0x57F287)
      .setTitle('✅  Ban levé')
      .setDescription(`> **Utilisateur :** ${ban.user.tag}`)
      .setFooter({ text: `ID : ${ban.user.id}` })
      .setTimestamp();
    await ch.send({ embeds: [embed] });
  } catch(e) { console.error('Log unban error:', e.message); }
});

// ═══════════════════════════════════════════════════════════
//  MESSAGE CREATE — Commandes (OWNER ONLY)
// ═══════════════════════════════════════════════════════════
client.on('messageCreate', async (message) => {
  if (message.author.bot) return;

  // ─── DM : réponse questionnaire ──────────────────────────
  if (!message.guild) {
    const session = sessions.get(message.author.id);
    if (!session) return;
    if (session.awaitingGuild) return; // On attend une selection de guild
    const step = STEPS[session.step];
    if (!step || step.type !== 'text') return;

    session.data[step.key] = message.content.trim();
    session.step++;

    if (session.step >= STEPS.length) {
      return message.reply({ embeds: [embedSummary(session.data)], components: [rowConfirm()] });
    }

    const nextStep = STEPS[session.step];
    return message.reply({
      embeds: [embedQuestion(session.step + 1, STEPS.length, nextStep)],
      components: getRowForStep(nextStep)
    });
  }

  // ─── OWNER ONLY : vérification ────────────────────────────
  if (message.author.id !== CONFIG.ownerId) return;

  if (!message.content.startsWith(CONFIG.prefix)) return;
  const args = message.content.slice(CONFIG.prefix.length).trim().split(/ +/);
  const cmd  = args.shift().toLowerCase();

  // ── +help ─────────────────────────────────────────────────
  if (cmd === 'help') {
    return message.channel.send({
      embeds: [embedPanel(client)],
      components: [rowPanelButtons(client.user.id)]
    });
  }

  // ── +points ───────────────────────────────────────────────
  if (cmd === 'points') {
    const pts  = DB.getPoints(message.author.id);
    const gens = DB.getGens(message.author.id);
    return message.reply({ embeds: [embedBase('◈  Vos crédits',
      `> 🪙 **Crédits :** \`${pts}\`\n> ⚡ **Générations :** \`${gens}\``
    )] });
  }

  // ── +generate ─────────────────────────────────────────────
  if (cmd === 'generate') {
    if (sessions.has(message.author.id))
      return message.reply({ embeds: [embedWarn('Session active', '> Tu as déjà un questionnaire en cours dans tes DMs.')] });

    // Récupérer les guilds où le bot est présent et où l'utilisateur est admin
    const allGuilds = [...client.guilds.cache.values()];

    if (allGuilds.length === 0) {
      return message.reply({ embeds: [embedErr('Aucun serveur', '> Le bot n\'est sur aucun serveur. Ajoute-le d\'abord via le bouton dans `+help`.')] });
    }

    // Créer une session en attente de selection de guild
    sessions.set(message.author.id, { step: 0, data: {}, guildId: null, awaitingGuild: true });

    const guildsArray = allGuilds;

    try {
      await message.author.send({
        embeds: [embedGuildSelect(guildsArray)],
        components: [rowGuildSelect(guildsArray)]
      });
      return message.reply({ embeds: [embedOk('Sélection du serveur', '> Choisis le serveur cible dans tes **DMs** !')] });
    } catch {
      sessions.delete(message.author.id);
      return message.reply({ embeds: [embedErr('DMs fermés', '> Active tes messages privés et réessaie.')] });
    }
  }

  // ── +addpoints ────────────────────────────────────────────
  if (cmd === 'addpoints') {
    const user   = message.mentions.users.first();
    const amount = parseInt(args[1]);
    if (!user || isNaN(amount)) return message.reply({ embeds: [embedWarn('Usage', '> `+addpoints @user nombre`')] });
    DB.addPoints(user.id, amount);
    return message.reply({ embeds: [embedOk('Crédits ajoutés', `> ✅ **+${amount}** crédits → ${user}\n> **Total :** \`${DB.getPoints(user.id)}\``)] });
  }

  // ── +removepoints ─────────────────────────────────────────
  if (cmd === 'removepoints') {
    const user   = message.mentions.users.first();
    const amount = parseInt(args[1]);
    if (!user || isNaN(amount)) return message.reply({ embeds: [embedWarn('Usage', '> `+removepoints @user nombre`')] });
    DB.removePoints(user.id, amount);
    return message.reply({ embeds: [embedOk('Crédits retirés', `> ✅ **-${amount}** crédits → ${user}\n> **Total :** \`${DB.getPoints(user.id)}\``)] });
  }

  // ── +resetuser ────────────────────────────────────────────
  if (cmd === 'resetuser') {
    const user = message.mentions.users.first();
    if (!user) return message.reply({ embeds: [embedWarn('Usage', '> `+resetuser @user`')] });
    DB.resetUser(user.id);
    return message.reply({ embeds: [embedOk('Reset effectué', `> ✅ ${user} a été réinitialisé.`)] });
  }

  // ── +setlogs ──────────────────────────────────────────────
  if (cmd === 'setlogs') {
    const sub = args[0];
    const ch  = message.mentions.channels.first();
    if (!sub || !ch) return message.reply({ embeds: [embedWarn('Usage', '> `+setlogs [join|leave|mod|msg|srv] #salon`')] });

    const current = DB.getLogsConfig(message.guild.id) || {};
    const keyMap  = { join: 'joinChannelId', leave: 'leaveChannelId', mod: 'modChannelId', msg: 'msgChannelId', srv: 'srvChannelId' };
    if (!keyMap[sub]) return message.reply({ embeds: [embedWarn('Type invalide', '> Types : `join`, `leave`, `mod`, `msg`, `srv`')] });

    current[keyMap[sub]] = ch.id;
    DB.setLogsConfig(message.guild.id, current);
    return message.reply({ embeds: [embedOk('Logs mis à jour', `> ✅ Logs \`${sub}\` → ${ch}`)] });
  }
});

// ═══════════════════════════════════════════════════════════
//  INTERACTION CREATE
// ═══════════════════════════════════════════════════════════
client.on('interactionCreate', async (interaction) => {

  // ─── Bouton panel : Générer un serveur ───────────────────
  if (interaction.isButton() && interaction.customId === 'btn_start') {
    if (sessions.has(interaction.user.id))
      return interaction.reply({ embeds: [embedWarn('Session active', '> Tu as déjà un questionnaire en cours dans tes DMs.')], ephemeral: true });

    // Tous les serveurs où le bot est présent
    const allGuilds = [...client.guilds.cache.values()];

    if (allGuilds.length === 0)
      return interaction.reply({ embeds: [embedErr('Aucun serveur', '> Le bot n\'est sur aucun serveur. Ajoute-le via le bouton ci-dessus.')], ephemeral: true });

    sessions.set(interaction.user.id, { step: 0, data: {}, guildId: null, awaitingGuild: true });
    const guildsArray = allGuilds;

    try {
      await interaction.user.send({
        embeds: [embedGuildSelect(guildsArray)],
        components: [rowGuildSelect(guildsArray)]
      });
      return interaction.reply({ embeds: [embedOk('Sélection du serveur', '> Choisis le serveur cible dans tes **DMs** !')], ephemeral: true });
    } catch {
      sessions.delete(interaction.user.id);
      return interaction.reply({ embeds: [embedErr('DMs fermés', '> Active tes messages privés.')], ephemeral: true });
    }
  }

  // ─── Select : Choix du serveur cible ────────────────────
  if (interaction.isStringSelectMenu() && interaction.customId === 'sel_guild') {
    const session = sessions.get(interaction.user.id);
    if (!session) return interaction.reply({ content: 'Session expirée.', ephemeral: true });

    session.guildId      = interaction.values[0];
    session.awaitingGuild = false;

    const guild = client.guilds.cache.get(session.guildId);
    if (!guild) {
      sessions.delete(interaction.user.id);
      return interaction.update({ embeds: [embedErr('Serveur introuvable', '> Impossible de trouver ce serveur.')], components: [] });
    }

    await interaction.update({ embeds: [embedBase('◈  Serveur sélectionné', `> ✅ Serveur : **${guild.name}**\n\n> Le questionnaire va démarrer...`)], components: [] });

    const firstStep = STEPS[0];
    return interaction.followUp({
      embeds: [embedQuestion(1, STEPS.length, firstStep)],
      components: getRowForStep(firstStep)
    });
  }

  // ─── Select menus questionnaire (dans DMs) ───────────────
  if (interaction.isStringSelectMenu() && ['sel_style','sel_features','sel_finish'].includes(interaction.customId)) {
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
    return interaction.followUp({
      embeds: [embedQuestion(session.step + 1, STEPS.length, nextStep)],
      components: getRowForStep(nextStep)
    });
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
      return interaction.update({ embeds: [embedErr('Permissions manquantes', '> Le bot doit être **Administrateur** sur le serveur cible.')], components: [] });
    }

    await interaction.update({
      embeds: [embedBase('◈  Génération en cours...', '`▓▓▓▓▓░░░░░` 50% — Construction de la structure...\n\n*Patiente quelques secondes.*')],
      components: []
    });

    try {
      // Appel Claude API pour plan unique
      let plan = null;
      if (CONFIG.anthropicKey) {
        await interaction.editReply({
          embeds: [embedBase('◈  Génération en cours...', '`▓▓▓░░░░░░░` 30% — Personnalisation en cours...\n\n*Patiente quelques secondes.*')]
        });
        plan = await generateServerPlan(session.data);
      }

      await interaction.editReply({
        embeds: [embedBase('◈  Génération en cours...', '`▓▓▓▓▓▓░░░░` 60% — Construction des salons et rôles...\n\n*Patiente quelques secondes.*')]
      });

      const { stats } = await buildServer(guild, session.data, plan);

      DB.incGens(interaction.user.id);
      sessions.delete(interaction.user.id);

      return interaction.editReply({
        embeds: [embedOk('◈  Génération terminée ✓',
          `**${session.data.serverName}** est prêt sur **${guild.name}** !\n\n` +
          `> 📂 **Catégories :** ${stats.categories}\n` +
          `> 💬 **Salons :** ${stats.channels}\n` +
          `> 🎭 **Rôles :** ${stats.roles}\n` +
          `> ⚙️ **Salons configurés :** ${stats.configured}`
        )]
      });
    } catch (err) {
      sessions.delete(interaction.user.id);
      console.error('Build error:', err);
      return interaction.editReply({ embeds: [embedErr('Erreur', `> \`${err.message}\``)] });
    }
  }

  // ─── Bouton : Annuler ─────────────────────────────────────
  if (interaction.isButton() && interaction.customId === 'btn_cancel') {
    sessions.delete(interaction.user.id);
    return interaction.update({ embeds: [embedWarn('Annulé', '> La génération a été annulée.')], components: [] });
  }

  // ═══════════════════════════════════════════════════════
  //  SYSTÈME TICKETS
  // ═══════════════════════════════════════════════════════

  // ─── Ouvrir un ticket ────────────────────────────────────
  if (interaction.isButton() && interaction.customId === 'ticket_open') {
    const config = DB.getTicketConfig(interaction.guild.id);
    if (!config) return interaction.reply({ content: 'Système de tickets non configuré.', ephemeral: true });

    // Vérifier si l'user a déjà un ticket ouvert
    const existing = interaction.guild.channels.cache.find(c =>
      c.name === `ticket-${interaction.user.username.toLowerCase().replace(/[^a-z0-9]/g, '')}` ||
      (DB.getTicket(c.id)?.userId === interaction.user.id && DB.getTicket(c.id)?.status === 'open')
    );

    if (existing)
      return interaction.reply({ embeds: [embedWarn('Ticket existant', `> Tu as déjà un ticket ouvert : ${existing}`)], ephemeral: true });

    await interaction.deferReply({ ephemeral: true });

    const ticketNum = DB.incTicketCount(interaction.guild.id);
    const everyoneId = interaction.guild.roles.everyone.id;

    const overwrites = [
      { id: everyoneId, deny: [PermissionFlagsBits.ViewChannel] },
      { id: interaction.user.id, allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages, PermissionFlagsBits.ReadMessageHistory] }
    ];

    if (config.modRoleId)   overwrites.push({ id: config.modRoleId,   allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages] });
    if (config.adminRoleId) overwrites.push({ id: config.adminRoleId, allow: [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages] });

    // Trouver la catégorie support
    const supportCat = interaction.guild.channels.cache.find(c =>
      c.type === ChannelType.GuildCategory && c.name.toLowerCase().includes('support')
    );

    const ticketCh = await interaction.guild.channels.create({
      name: `🎫-ticket-${ticketNum.toString().padStart(4,'0')}`,
      type: ChannelType.GuildText,
      parent: supportCat?.id,
      permissionOverwrites: overwrites,
      topic: `Ticket de ${interaction.user.tag} — #${ticketNum}`,
      reason: `Ticket ouvert par ${interaction.user.tag}`
    });

    DB.setTicket(ticketCh.id, {
      userId: interaction.user.id,
      userTag: interaction.user.tag,
      number: ticketNum,
      status: 'open',
      openedAt: Date.now(),
      claimedBy: null
    });

    const ticketEmbed = new EmbedBuilder()
      .setColor(CONFIG.color)
      .setTitle(`🎫  Ticket #${ticketNum}`)
      .setDescription(
        `> Bienvenue ${interaction.user} !\n` +
        '> Un membre du staff va te répondre sous peu.\n\n' +
        '> **Décris ton problème ou ta demande ci-dessous.**'
      )
      .addFields(
        { name: 'Ouvert par', value: `${interaction.user}`, inline: true },
        { name: 'Date',       value: `<t:${Math.floor(Date.now()/1000)}:F>`, inline: true }
      )
      .setFooter({ text: 'Generate  •  Support' })
      .setTimestamp();

    const ticketRow = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('ticket_close').setLabel('Fermer').setEmoji('🔒').setStyle(ButtonStyle.Danger),
      new ButtonBuilder().setCustomId('ticket_claim').setLabel('Prendre en charge').setEmoji('✋').setStyle(ButtonStyle.Secondary)
    );

    await ticketCh.send({ content: `${interaction.user}`, embeds: [ticketEmbed], components: [ticketRow] });
    return interaction.editReply({ embeds: [embedOk('Ticket ouvert', `> ✅ Ton ticket a été créé : ${ticketCh}`)] });
  }

  // ─── Fermer un ticket ────────────────────────────────────
  if (interaction.isButton() && interaction.customId === 'ticket_close') {
    const ticketData = DB.getTicket(interaction.channel.id);
    if (!ticketData) return interaction.reply({ content: 'Ce salon n\'est pas un ticket.', ephemeral: true });

    const config = DB.getTicketConfig(interaction.guild.id);
    const isMod  = config?.modRoleId && interaction.member.roles.cache.has(config.modRoleId);
    const isAdmin = config?.adminRoleId && interaction.member.roles.cache.has(config.adminRoleId);
    const isOwner = interaction.user.id === ticketData.userId;

    if (!isMod && !isAdmin && !isOwner && interaction.user.id !== CONFIG.ownerId)
      return interaction.reply({ embeds: [embedErr('Permission refusée', '> Tu ne peux pas fermer ce ticket.')], ephemeral: true });

    await interaction.deferReply();

    // Log du ticket
    if (config?.logChannelId) {
      try {
        const logCh = await interaction.guild.channels.fetch(config.logChannelId).catch(() => null);
        if (logCh) {
          const msgs = await interaction.channel.messages.fetch({ limit: 50 }).catch(() => null);
          const transcript = msgs
            ? [...msgs.values()].reverse()
                .filter(m => !m.author.bot)
                .map(m => `[${new Date(m.createdTimestamp).toLocaleString('fr-FR')}] ${m.author.tag}: ${m.content || '[embed/fichier]'}`)
                .join('\n')
                .slice(0, 3000)
            : 'Aucun message';

          const logEmbed = new EmbedBuilder()
            .setColor(0xED4245)
            .setTitle(`🔒  Ticket #${ticketData.number} fermé`)
            .setDescription(
              `> **Ouvert par :** ${ticketData.userTag}\n` +
              `> **Fermé par :** ${interaction.user.tag}\n` +
              `> **Durée :** ${Math.round((Date.now() - ticketData.openedAt) / 60000)} minutes\n\n` +
              `**Transcript (50 derniers msgs) :**\n\`\`\`\n${transcript}\n\`\`\``
            )
            .setTimestamp();
          await logCh.send({ embeds: [logEmbed] });
        }
      } catch(e) { console.error('Ticket log error:', e.message); }
    }

    await interaction.editReply({ embeds: [embedWarn('Fermeture', '> Ce ticket sera supprimé dans **5 secondes**...')] });
    DB.delTicket(interaction.channel.id);
    await sleep(5000);
    await interaction.channel.delete('Ticket fermé').catch(() => {});
  }

  // ─── Prendre en charge un ticket ─────────────────────────
  if (interaction.isButton() && interaction.customId === 'ticket_claim') {
    const ticketData = DB.getTicket(interaction.channel.id);
    if (!ticketData) return interaction.reply({ content: 'Ce salon n\'est pas un ticket.', ephemeral: true });

    const config  = DB.getTicketConfig(interaction.guild.id);
    const isMod   = config?.modRoleId && interaction.member.roles.cache.has(config.modRoleId);
    const isAdmin = config?.adminRoleId && interaction.member.roles.cache.has(config.adminRoleId);

    if (!isMod && !isAdmin && interaction.user.id !== CONFIG.ownerId)
      return interaction.reply({ embeds: [embedErr('Permission refusée', '> Seul le staff peut prendre en charge un ticket.')], ephemeral: true });

    if (ticketData.claimedBy)
      return interaction.reply({ embeds: [embedWarn('Déjà pris en charge', `> Ce ticket est déjà géré par <@${ticketData.claimedBy}>.`)], ephemeral: true });

    ticketData.claimedBy = interaction.user.id;
    DB.setTicket(interaction.channel.id, ticketData);

    return interaction.reply({ embeds: [embedOk('Pris en charge', `> ✅ ${interaction.user} prend en charge ce ticket.`)] });
  }
});

// ═══════════════════════════════════════════════════════════
//  BOOST — 2 jetons quand un membre boost
// ═══════════════════════════════════════════════════════════
client.on('guildMemberUpdate', async (oldMember, newMember) => {
  // Détecte si le membre vient de booster (pas de boost avant, boost maintenant)
  const wasBooster = !!oldMember.premiumSince;
  const isBooster  = !!newMember.premiumSince;

  if (!wasBooster && isBooster) {
    DB.addPoints(newMember.id, 2);

    // Chercher un salon logs ou général pour notifier
    const logsConfig = DB.getLogsConfig(newMember.guild.id);
    const notifChId  = logsConfig?.joinChannelId || logsConfig?.modChannelId;

    if (notifChId) {
      try {
        const ch = await newMember.guild.channels.fetch(notifChId).catch(() => null);
        if (ch) {
          const embed = new EmbedBuilder()
            .setColor(0xF8B500)
            .setTitle('💎  Nouveau Booster !')
            .setDescription(
              `> ${newMember} vient de **booster** le serveur !\n` +
              `> 🪙 **+2 jetons** ont été ajoutés à son compte.\n` +
              '> **Total :** `' + DB.getPoints(newMember.id) + '` jetons'
            )
            .setThumbnail(newMember.user.displayAvatarURL({ size: 128 }))
            .setFooter({ text: 'Generate  •  Merci pour ton boost !' })
            .setTimestamp();
          await ch.send({ embeds: [embed] });
        }
      } catch(e) { console.error('Boost notif error:', e.message); }
    }
  }
});

// ═══════════════════════════════════════════════════════════
//  BOOST — 2 jetons quand un membre boost
// ═══════════════════════════════════════════════════════════
client.on('guildMemberUpdate', async (oldMember, newMember) => {
  const wasBooster = !!oldMember.premiumSince;
  const isBooster  = !!newMember.premiumSince;
  if (!wasBooster && isBooster) {
    DB.addPoints(newMember.id, 2);
    const logsConfig = DB.getLogsConfig(newMember.guild.id);
    const notifChId  = logsConfig?.joinChannelId || logsConfig?.modChannelId;
    if (notifChId) {
      try {
        const ch = await newMember.guild.channels.fetch(notifChId).catch(() => null);
        if (ch) {
          const embed = new EmbedBuilder()
            .setColor(0xF8B500)
            .setTitle('💎  Nouveau Booster !')
            .setDescription(
              `> ${newMember} vient de **booster** le serveur !\n` +
              `> 🪙 **+2 jetons** ont été ajoutés à son compte.\n` +
              `> **Total :** \`${DB.getPoints(newMember.id)}\` jetons`
            )
            .setThumbnail(newMember.user.displayAvatarURL({ size: 128 }))
            .setFooter({ text: 'Generate  •  Merci pour ton boost !' })
            .setTimestamp();
          await ch.send({ embeds: [embed] });
        }
      } catch(e) { console.error('Boost notif error:', e.message); }
    }
  }
});

// ═══════════════════════════════════════════════════════════
//  ANTI-CRASH
// ═══════════════════════════════════════════════════════════
process.on('unhandledRejection', err => console.error('Rejection:', err?.message || err));
process.on('uncaughtException',  err => console.error('Exception:', err?.message || err));

// ═══════════════════════════════════════════════════════════
//  LOGIN
// ═══════════════════════════════════════════════════════════
if (!CONFIG.token) {
  console.error('❌ TOKEN manquant dans les variables d\'environnement');
  process.exit(1);
}

client.login(CONFIG.token)
  .then(() => console.log('✅ Generate connecté !'))
  .catch(err => { console.error('❌ Login failed:', err.message); process.exit(1); });
