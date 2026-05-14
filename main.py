'use strict';
require('dotenv').config();

// ╔══════════════════════════════════════════════════════════╗
// ║              GENERATE BOT  —  index.js                  ║
// ║         discord.js v14  •  Node.js  •  Railway          ║
// ╚══════════════════════════════════════════════════════════╝

const {
  Client, GatewayIntentBits, Partials,
  EmbedBuilder, ActionRowBuilder,
  ButtonBuilder, ButtonStyle,
  StringSelectMenuBuilder,
  PermissionFlagsBits, ChannelType, ActivityType,
} = require('discord.js');
const Database = require('better-sqlite3');
const Groq     = require('groq-sdk');
const path     = require('path');

// ══════════════════════════════════════════════════════════
//  CONFIG
// ══════════════════════════════════════════════════════════

const OWNERS = [
  '1191963306785787946',
  '1390042531928080544',
];

const CFG = {
  prefix:          process.env.PREFIX        || '+',
  mainGuildId:     process.env.MAIN_GUILD_ID || '',
  mainInvite:      'https://discord.gg/2PvXETvFFG',
  boostBonus:      5,
  questionTimeout: 90_000,
  generateCooldown: 60,
  groqModel:       'llama-3.3-70b-versatile',

  colors: {
    primary:  0x1E1F22,
    accent:   0x5865F2,
    success:  0x57F287,
    error:    0xED4245,
    warning:  0xFEE75C,
    premium:  0xF0B232,
    info:     0x2B2D31,
  },
};

// ══════════════════════════════════════════════════════════
//  LOGGER
// ══════════════════════════════════════════════════════════

const log = {
  _ts:   () => `\x1b[90m${new Date().toLocaleTimeString('fr-FR')}\x1b[0m`,
  info:  (...a) => console.log (`${log._ts()} \x1b[1m\x1b[36m[INFO]\x1b[0m`, ...a),
  ok:    (...a) => console.log (`${log._ts()} \x1b[1m\x1b[32m[ OK ]\x1b[0m`, ...a),
  warn:  (...a) => console.warn(`${log._ts()} \x1b[1m\x1b[33m[WARN]\x1b[0m`, ...a),
  error: (...a) => console.error(`${log._ts()} \x1b[1m\x1b[31m[ERR ]\x1b[0m`, ...a),
};

// ══════════════════════════════════════════════════════════
//  BASE DE DONNÉES  (better-sqlite3)
// ══════════════════════════════════════════════════════════

const db = new Database(path.join(__dirname, 'generate.db'));
db.pragma('journal_mode = WAL');
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id             TEXT PRIMARY KEY,
    username       TEXT    DEFAULT 'Inconnu',
    points         INTEGER DEFAULT 0,
    invite_credits INTEGER DEFAULT 0,
    generations    INTEGER DEFAULT 0,
    last_gen       INTEGER DEFAULT 0,
    created_at     INTEGER DEFAULT (unixepoch())
  );
  CREATE TABLE IF NOT EXISTS generations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    TEXT    NOT NULL,
    guild_id   TEXT    NOT NULL,
    style      TEXT,
    name       TEXT,
    created_at INTEGER DEFAULT (unixepoch())
  );
`);

const stmts = {
  get:        db.prepare('SELECT * FROM users WHERE id = ?'),
  insert:     db.prepare('INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)'),
  updName:    db.prepare('UPDATE users SET username = ? WHERE id = ?'),
  addPts:     db.prepare('UPDATE users SET points = MAX(0, points + ?) WHERE id = ?'),
  remPts:     db.prepare('UPDATE users SET points = MAX(0, points - ?) WHERE id = ?'),
  addCreds:   db.prepare('UPDATE users SET invite_credits = MAX(0, invite_credits + ?) WHERE id = ?'),
  useCred:    db.prepare('UPDATE users SET invite_credits = invite_credits - 1 WHERE id = ?'),
  usePt:      db.prepare('UPDATE users SET points = points - 1 WHERE id = ?'),
  reset:      db.prepare('UPDATE users SET points=0,invite_credits=0,generations=0,last_gen=0 WHERE id=?'),
  setLastGen: db.prepare('UPDATE users SET generations=generations+1, last_gen=unixepoch() WHERE id=?'),
  logGen:     db.prepare('INSERT INTO generations(user_id,guild_id,style,name) VALUES(?,?,?,?)'),
};

const DB = {
  ensure(id, name = 'Inconnu') {
    stmts.insert.run(id, name);
    if (name !== 'Inconnu') stmts.updName.run(name, id);
    return stmts.get.get(id);
  },
  get:          (id)        => stmts.get.get(id),
  addPoints:    (id, n)     => { stmts.addPts.run(n, id); return stmts.get.get(id); },
  removePoints: (id, n)     => { stmts.remPts.run(n, id); return stmts.get.get(id); },
  addCredits:   (id, n)     => stmts.addCreds.run(n, id),
  reset:        (id)        => stmts.reset.run(id),
  totalUses:    (id)        => { const u = stmts.get.get(id); return u ? u.points + u.invite_credits : 0; },

  consume(id) {
    const u = stmts.get.get(id);
    if (!u) return false;
    if (u.invite_credits > 0) { stmts.useCred.run(id); return true; }
    if (u.points > 0)         { stmts.usePt.run(id);   return true; }
    return false;
  },

  recordGen(userId, guildId, style, name) {
    stmts.setLastGen.run(userId);
    stmts.logGen.run(userId, guildId, style, name);
  },
};

// ══════════════════════════════════════════════════════════
//  PERMISSIONS
// ══════════════════════════════════════════════════════════

const isOwner = (id) => OWNERS.includes(id);

async function isInMainGuild(client, userId) {
  if (!CFG.mainGuildId) return false;
  try {
    const guild = await client.guilds.fetch(CFG.mainGuildId).catch(() => null);
    if (!guild) return false;
    return !!(await guild.members.fetch(userId).catch(() => null));
  } catch { return false; }
}

// ══════════════════════════════════════════════════════════
//  COOLDOWN
// ══════════════════════════════════════════════════════════

const cdMap = new Map();

function checkCooldown(userId, cmd, secs) {
  if (!secs) return 0;
  const key = `${cmd}:${userId}`;
  const now = Date.now();
  const exp = cdMap.get(key) ?? 0;
  if (exp > now) return Math.ceil((exp - now) / 1000);
  cdMap.set(key, now + secs * 1000);
  setTimeout(() => cdMap.delete(key), secs * 1000);
  return 0;
}

// ══════════════════════════════════════════════════════════
//  EMBEDS  (style premium Generate)
// ══════════════════════════════════════════════════════════

const FOOTER = { text: '⚡ Generate' };

function base(color) {
  return new EmbedBuilder().setColor(color).setFooter(FOOTER).setTimestamp();
}

const E = {
  ok:      (t, d) => base(CFG.colors.success).setTitle(`✅  ${t}`).setDescription(d ?? ''),
  err:     (t, d) => base(CFG.colors.error).setTitle(`❌  ${t}`).setDescription(d ?? ''),
  warn:    (t, d) => base(CFG.colors.warning).setTitle(`⚠️  ${t}`).setDescription(d ?? ''),
  info:    (t, d) => base(CFG.colors.accent).setTitle(`ℹ️  ${t}`).setDescription(d ?? ''),
  premium: (t, d) => base(CFG.colors.premium).setTitle(`👑  ${t}`).setDescription(d ?? ''),
  load:    (t, d) => base(CFG.colors.info).setTitle(`⏳  ${t}`).setDescription(d ?? ''),

  question(step, total, title, desc) {
    return new EmbedBuilder()
      .setColor(CFG.colors.accent)
      .setAuthor({ name: `Étape ${step} / ${total}` })
      .setTitle(`『⚙️』 ${title}`)
      .setDescription(`${desc}\n\n> ⏱️ *Vous avez 90 secondes pour répondre.*`)
      .setFooter(FOOTER)
      .setTimestamp();
  },
};

// ══════════════════════════════════════════════════════════
//  GROQ  —  Génération de la structure serveur
// ══════════════════════════════════════════════════════════

async function buildStructure(answers) {
  const groq = new Groq({ apiKey: process.env.API_KEY });

  const prompt = `
Tu es un expert en architecture de serveurs Discord. Génère une structure complète et professionnelle.
RÉPONDS UNIQUEMENT en JSON valide. Zéro texte en dehors du JSON.

Informations du serveur :
- Nom : ${answers.name}
- Thème : ${answers.theme}
- Membres prévus : ${answers.members}
- Langue : ${answers.language}
- Nombre de rôles : ${answers.roleCount}
- Style : ${answers.style}
- Fonctionnalités : ${answers.features.join(', ')}
- Niveau de finition : ${answers.finish}
- Couleurs : ${answers.colors}
- Fondateur : ${answers.founder}

Règles de nommage OBLIGATOIRES :
- Catégories : MAJUSCULES avec emoji, ex : "『📢』INFORMATIONS"
- Salons texte : minuscules-tirets avec emoji, ex : "『📢』annonces"
- Salons vocal : minuscules-tirets avec emoji, ex : "『🔊』vocal-1"
- Rôles : avec emoji au début, ex : "『👑』Fondateur"
- Couleurs hex valides uniquement

JSON attendu (schéma EXACT) :
{
  "categories": [
    {
      "name": "string",
      "staffOnly": false,
      "channels": [
        {
          "name": "string",
          "type": "text|voice|announcement",
          "topic": "string",
          "slowmode": 0,
          "nsfw": false,
          "staffOnly": false
        }
      ]
    }
  ],
  "roles": [
    {
      "name": "string",
      "color": "#RRGGBB",
      "hoist": true,
      "mentionable": false,
      "admin": false,
      "mod": false
    }
  ],
  "welcomeMessage": "string",
  "rules": ["string"],
  "description": "string"
}

Adapte tout au style "${answers.style}" et au thème "${answers.theme}".
Finition "${answers.finish}" :
- simple → 4 catégories, 6+ rôles
- avancé → 6 catégories, 10+ rôles
- ultra premium → 8+ catégories, 15+ rôles, maximum de détails
Inclure les fonctionnalités demandées sous forme de salons dédiés.
Sois créatif, moderne et professionnel.
`.trim();

  for (let i = 0; i < 3; i++) {
    try {
      const res = await groq.chat.completions.create({
        model: CFG.groqModel,
        messages: [{ role: 'user', content: prompt }],
        response_format: { type: 'json_object' },
        temperature: 0.85,
        max_tokens: 4096,
      });
      return JSON.parse(res.choices[0].message.content);
    } catch (err) {
      if (i === 2) throw err;
      log.warn(`Retry Groq (${i + 1}/3)...`);
      await sleep(2500 * (i + 1));
    }
  }
}

// ══════════════════════════════════════════════════════════
//  APPLICATION DE LA STRUCTURE SUR DISCORD
// ══════════════════════════════════════════════════════════

async function applyStructure(guild, struct, onStep) {
  const everyone = guild.roles.everyone;

  await onStep('🗑️  Suppression des salons existants...');
  await Promise.allSettled([...guild.channels.cache.values()].map(c => c.delete().catch(() => {})));

  await onStep('🗑️  Suppression des rôles existants...');
  for (const r of guild.roles.cache.values()) {
    if (r.id !== everyone.id && !r.managed) await r.delete().catch(() => {});
  }

  await onStep('🎭  Création des rôles...');
  let staffRole = null;
  for (const r of [...(struct.roles ?? [])].reverse()) {
    try {
      const perms = r.admin
        ? [PermissionFlagsBits.Administrator]
        : r.mod
          ? [PermissionFlagsBits.ManageMessages, PermissionFlagsBits.KickMembers, PermissionFlagsBits.BanMembers, PermissionFlagsBits.ViewChannel]
          : [PermissionFlagsBits.ViewChannel, PermissionFlagsBits.SendMessages];

      const role = await guild.roles.create({
        name: r.name,
        color: /^#[0-9A-F]{6}$/i.test(r.color) ? r.color : '#99AAB5',
        hoist: r.hoist ?? false,
        mentionable: r.mentionable ?? false,
        permissions: perms,
      });
      if (r.mod && !staffRole) staffRole = role;
    } catch { /* rôle ignoré */ }
  }

  await onStep('📁  Création des catégories et salons...');
  for (const cat of struct.categories ?? []) {
    try {
      const catPerms = cat.staffOnly
        ? [{ id: everyone.id, deny: [PermissionFlagsBits.ViewChannel] },
           ...(staffRole ? [{ id: staffRole.id, allow: [PermissionFlagsBits.ViewChannel] }] : [])]
        : [];

      const category = await guild.channels.create({
        name: cat.name,
        type: ChannelType.GuildCategory,
        permissionOverwrites: catPerms,
      });

      for (const ch of cat.channels ?? []) {
        const chanPerms = ch.staffOnly
          ? [{ id: everyone.id, deny: [PermissionFlagsBits.ViewChannel] }]
          : [];

        await guild.channels.create({
          name: ch.name,
          type: ch.type === 'voice'
            ? ChannelType.GuildVoice
            : ch.type === 'announcement'
              ? ChannelType.GuildAnnouncement
              : ChannelType.GuildText,
          parent: category,
          topic: ch.topic ?? '',
          rateLimitPerUser: ch.slowmode ?? 0,
          nsfw: ch.nsfw ?? false,
          permissionOverwrites: chanPerms,
        }).catch(() => {});

        await sleep(300); // évite le rate-limit Discord
      }
    } catch { /* catégorie ignorée */ }
  }

  await onStep('📝  Envoi du règlement et bienvenue...');
  const firstText = guild.channels.cache.find(c => c.type === ChannelType.GuildText);

  if (firstText && struct.welcomeMessage) {
    await firstText.send({ content: struct.welcomeMessage }).catch(() => {});
  }

  const rulesChan = guild.channels.cache.find(c =>
    c.type === ChannelType.GuildText &&
    (c.name.includes('règl') || c.name.includes('regles') || c.name.includes('rules'))
  );
  if (rulesChan && struct.rules?.length) {
    const txt = struct.rules.map((r, i) => `**${i + 1}.** ${r}`).join('\n\n');
    await rulesChan.send({ content: `📜 **Règlement du serveur**\n\n${txt}` }).catch(() => {});
  }

  return firstText;
}

// ══════════════════════════════════════════════════════════
//  QUESTIONNAIRE INTERACTIF
// ══════════════════════════════════════════════════════════

const activeGen = new Set();

const cancelRow = () => new ActionRowBuilder().addComponents(
  new ButtonBuilder().setCustomId('q_cancel').setLabel('Annuler').setStyle(ButtonStyle.Danger).setEmoji('✖️')
);

async function collectText(channel, userId, msgRef, timeout) {
  const cancelP = msgRef.awaitMessageComponent({
    filter: i => i.user.id === userId && i.customId === 'q_cancel',
    time: timeout,
  }).then(i => { i.deferUpdate(); return 'CANCEL'; }).catch(() => null);

  const textP = channel.awaitMessages({
    filter: m => m.author.id === userId && !m.author.bot,
    max: 1, time: timeout, errors: ['time'],
  }).then(async c => {
    const m = c.first();
    await m.delete().catch(() => {});
    return { value: m.content.trim() };
  }).catch(() => ({ value: null }));

  const result = await Promise.race([cancelP, textP]);
  if (result === 'CANCEL' || result?.value === null) return null;
  return result.value;
}

async function collectSelect(msgRef, userId, timeout) {
  try {
    const i = await msgRef.awaitMessageComponent({
      filter: i => i.user.id === userId && i.isStringSelectMenu(),
      time: timeout,
    });
    await i.deferUpdate();
    return i.values;
  } catch { return null; }
}

async function collectButton(msgRef, userId, timeout) {
  try {
    return await msgRef.awaitMessageComponent({
      filter: i => i.user.id === userId && i.isButton(),
      time: timeout,
    });
  } catch { return null; }
}

function selectRow(customId, placeholder, options, min = 1, max = 1) {
  return new ActionRowBuilder().addComponents(
    new StringSelectMenuBuilder()
      .setCustomId(customId)
      .setPlaceholder(placeholder)
      .setMinValues(min)
      .setMaxValues(max)
      .addOptions(options)
  );
}

async function runQuestionnaire(message) {
  const ch = message.channel;
  const u  = message.author;
  const T  = CFG.questionTimeout;
  const A  = {};

  // Envoie ou édite le message questionnaire
  let qMsg = await ch.send({
    embeds: [E.question(1, 10, 'Nom du serveur', '📝 **Quel est le nom de ton futur serveur Discord ?**\n\nTape ta réponse dans ce salon.')],
    components: [cancelRow()],
  });

  // ── Q1 : Nom ──────────────────────────────────────────
  A.name = await collectText(ch, u.id, qMsg, T);
  if (!A.name) return fin(qMsg, null);

  // ── Q2 : Thème ────────────────────────────────────────
  await qMsg.edit({ embeds: [E.question(2, 10, 'Thème du serveur', '🎨 **Quel est le thème principal ?**\n\n*Ex : gaming FPS, anime shōnen, e-commerce, communauté francophone...*')], components: [cancelRow()] });
  A.theme = await collectText(ch, u.id, qMsg, T);
  if (!A.theme) return fin(qMsg, null);

  // ── Q3 : Membres ─────────────────────────────────────
  await qMsg.edit({
    embeds: [E.question(3, 10, 'Membres prévus', '👥 **Combien de membres prévois-tu ?**')],
    components: [cancelRow(), selectRow('q_members', 'Sélectionne une tranche...', [
      { label: 'Moins de 10 membres',   value: 'moins de 10',  emoji: '👤' },
      { label: '10 à 50 membres',        value: '10 à 50',     emoji: '👥' },
      { label: '50 à 200 membres',       value: '50 à 200',    emoji: '🏘️' },
      { label: '200 à 1 000 membres',    value: '200 à 1000',  emoji: '🌆' },
      { label: 'Plus de 1 000 membres',  value: '1000+',       emoji: '🌍' },
    ])],
  });
  const mv = await collectSelect(qMsg, u.id, T);
  if (!mv) return fin(qMsg, null);
  A.members = mv[0];

  // ── Q4 : Langue ───────────────────────────────────────
  await qMsg.edit({
    embeds: [E.question(4, 10, 'Langue principale', '🌐 **Quelle est la langue principale du serveur ?**')],
    components: [cancelRow(), selectRow('q_lang', 'Choisis une langue...', [
      { label: 'Français',    value: 'Français',    emoji: '🇫🇷' },
      { label: 'Anglais',     value: 'Anglais',     emoji: '🇬🇧' },
      { label: 'Espagnol',    value: 'Espagnol',    emoji: '🇪🇸' },
      { label: 'Portugais',   value: 'Portugais',   emoji: '🇧🇷' },
      { label: 'Multilingue', value: 'Multilingue', emoji: '🌍' },
    ])],
  });
  const lv = await collectSelect(qMsg, u.id, T);
  if (!lv) return fin(qMsg, null);
  A.language = lv[0];

  // ── Q5 : Nombre de rôles ─────────────────────────────
  await qMsg.edit({
    embeds: [E.question(5, 10, 'Nombre de rôles', '🎭 **Combien de rôles souhaitez-vous ?**')],
    components: [cancelRow(), selectRow('q_roles', 'Choisis...', [
      { label: '5 rôles',    value: '5',  emoji: '🔹' },
      { label: '10 rôles',   value: '10', emoji: '🔸' },
      { label: '15 rôles',   value: '15', emoji: '💠' },
      { label: '20 rôles',   value: '20', emoji: '🌟' },
      { label: '25+ rôles',  value: '25', emoji: '👑' },
    ])],
  });
  const rv = await collectSelect(qMsg, u.id, T);
  if (!rv) return fin(qMsg, null);
  A.roleCount = rv[0];

  // ── Q6 : Style ────────────────────────────────────────
  await qMsg.edit({
    embeds: [E.question(6, 10, 'Style du serveur', '🎮 **Quel est le style de ton serveur ?**')],
    components: [cancelRow(), selectRow('q_style', 'Choisis un style...', [
      { label: 'Gaming',     value: 'gaming',     emoji: '🎮' },
      { label: 'Communauté', value: 'communauté', emoji: '💬' },
      { label: 'E-girl',     value: 'e-girl',     emoji: '🌸' },
      { label: 'Business',   value: 'business',   emoji: '💼' },
      { label: 'Chill',      value: 'chill',      emoji: '😌' },
      { label: 'Anime',      value: 'anime',      emoji: '🎌' },
      { label: 'Stream',     value: 'stream',     emoji: '📺' },
      { label: 'Autre',      value: 'autre',      emoji: '✨' },
    ])],
  });
  const sv = await collectSelect(qMsg, u.id, T);
  if (!sv) return fin(qMsg, null);
  A.style = sv[0];

  // ── Q7 : Fonctionnalités (multi) ─────────────────────
  await qMsg.edit({
    embeds: [E.question(7, 10, 'Fonctionnalités', '⚙️ **Quelles fonctionnalités souhaitez-vous ?**\n\n*Tu peux en sélectionner plusieurs.*')],
    components: [cancelRow(), selectRow('q_feats', 'Sélectionne les fonctionnalités...', [
      { label: 'Emojis dans les salons', value: 'emojis',       emoji: '😊' },
      { label: 'Catégories premium',      value: 'categories',   emoji: '📁' },
      { label: 'Rôles colorés',           value: 'roles',        emoji: '🎨' },
      { label: 'Salons vocaux',           value: 'vocal',        emoji: '🔊' },
      { label: 'Système de tickets',      value: 'tickets',      emoji: '🎫' },
      { label: 'Logs',                    value: 'logs',         emoji: '📋' },
      { label: 'Règlement',               value: 'reglement',    emoji: '📜' },
      { label: 'Annonces',                value: 'annonces',     emoji: '📢' },
      { label: 'Présentation',            value: 'presentation', emoji: '👤' },
      { label: 'Staff',                   value: 'staff',        emoji: '👑' },
      { label: 'Boosters',                value: 'boosters',     emoji: '🚀' },
      { label: 'Giveaways',               value: 'giveaways',    emoji: '🎁' },
      { label: 'Musique',                 value: 'musique',      emoji: '🎵' },
      { label: 'Bots',                    value: 'bots',         emoji: '🤖' },
    ], 1, 14)],
  });
  const fv = await collectSelect(qMsg, u.id, T);
  if (!fv) return fin(qMsg, null);
  A.features = fv;

  // ── Q8 : Finition ─────────────────────────────────────
  await qMsg.edit({
    embeds: [E.question(8, 10, 'Niveau de finition', '✨ **Quel niveau de finition souhaitez-vous ?**')],
    components: [cancelRow(), selectRow('q_finish', 'Choisis un niveau...', [
      { label: 'Simple',        value: 'simple',        emoji: '🔵', description: 'Structure propre et efficace' },
      { label: 'Avancé',        value: 'avancé',        emoji: '🟣', description: 'Structure complète et détaillée' },
      { label: 'Ultra Premium', value: 'ultra premium', emoji: '⭐', description: 'Maximum de contenu et personnalisation' },
    ])],
  });
  const fnv = await collectSelect(qMsg, u.id, T);
  if (!fnv) return fin(qMsg, null);
  A.finish = fnv[0];

  // ── Q9 : Couleurs ─────────────────────────────────────
  await qMsg.edit({ embeds: [E.question(9, 10, 'Couleurs dominantes', '🎨 **Quelles sont les couleurs dominantes ?**\n\n*Ex : noir, violet, doré — ou codes hex comme #1E1F22, #5865F2...*')], components: [cancelRow()] });
  A.colors = await collectText(ch, u.id, qMsg, T);
  if (!A.colors) return fin(qMsg, null);

  // ── Q10 : Fondateur ───────────────────────────────────
  await qMsg.edit({ embeds: [E.question(10, 10, 'Nom du fondateur', '👤 **Quel est le nom du fondateur du serveur ?**')], components: [cancelRow()] });
  A.founder = await collectText(ch, u.id, qMsg, T);
  if (!A.founder) return fin(qMsg, null);

  // ── Récapitulatif ─────────────────────────────────────
  const featLabels = {
    emojis:'Emojis', categories:'Catégories premium', roles:'Rôles colorés',
    vocal:'Salons vocaux', tickets:'Tickets', logs:'Logs', reglement:'Règlement',
    annonces:'Annonces', presentation:'Présentation', staff:'Staff',
    boosters:'Boosters', giveaways:'Giveaways', musique:'Musique', bots:'Bots',
  };

  const recap = new EmbedBuilder()
    .setColor(CFG.colors.premium)
    .setTitle('『👑』 Récapitulatif — Confirme ta configuration')
    .setDescription('> Vérifie les informations ci-dessous avant de lancer la génération.\n> ⚠️ **Le serveur sera entièrement restructuré.**\n​')
    .addFields(
      { name: '📛 Nom du serveur',   value: `\`${A.name}\``,                 inline: true },
      { name: '🎨 Thème',            value: `\`${A.theme}\``,                inline: true },
      { name: '👥 Membres prévus',   value: `\`${A.members}\``,              inline: true },
      { name: '🌐 Langue',           value: `\`${A.language}\``,             inline: true },
      { name: '🎭 Rôles',            value: `\`${A.roleCount} rôles\``,      inline: true },
      { name: '🎮 Style',            value: `\`${A.style}\``,                inline: true },
      { name: '✨ Finition',         value: `\`${A.finish}\``,               inline: true },
      { name: '🎨 Couleurs',         value: `\`${A.colors}\``,               inline: true },
      { name: '👤 Fondateur',        value: `\`${A.founder}\``,              inline: true },
      { name: '⚙️ Fonctionnalités',  value: A.features.map(f => featLabels[f] ?? f).join(', ') },
    )
    .setFooter(FOOTER)
    .setTimestamp();

  const confirmRow = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('q_confirm').setLabel('  Générer le serveur').setStyle(ButtonStyle.Success).setEmoji('⚡'),
    new ButtonBuilder().setCustomId('q_cancel').setLabel('Annuler').setStyle(ButtonStyle.Danger).setEmoji('✖️'),
  );

  await qMsg.edit({ embeds: [recap], components: [confirmRow] });

  const conf = await collectButton(qMsg, u.id, 60_000);
  if (!conf || conf.customId === 'q_cancel') {
    await conf?.deferUpdate();
    return fin(qMsg, null);
  }
  await conf.deferUpdate();
  await qMsg.edit({ components: [] });

  return { answers: A, qMsg };
}

async function fin(qMsg, val) {
  if (val === null) {
    await qMsg.edit({ embeds: [E.info('Questionnaire annulé', 'La génération a été annulée ou a expiré.')], components: [] }).catch(() => {});
  }
  return val;
}

// ══════════════════════════════════════════════════════════
//  COMMANDES
// ══════════════════════════════════════════════════════════

const CD = { help: 5, points: 5, invites: 5, generate: 60, addpoints: 0, removepoints: 0, resetuser: 0, forcegenerate: 0 };

async function cmdHelp(message) {
  const owner = isOwner(message.author.id);

  const embed = new EmbedBuilder()
    .setColor(CFG.colors.info)
    .setTitle('『⚡』 Generate — Panel d\'aide')
    .setDescription(
      '> **Generate** est le bot de référence pour créer des serveurs Discord\n' +
      '> professionnels, modernes et prêts à l\'emploi en quelques minutes.\n​'
    )
    .addFields(
      {
        name: '『🚀』 Commandes utilisateurs',
        value: [
          '`+generate` — Lance le configurateur interactif',
          '`+points` — Voir tes utilisations disponibles',
          '`+invites` — Voir tes invitations comptées',
          '`+help` — Ce panel d\'aide',
        ].join('\n'),
        inline: false,
      },
      {
        name: '『💎』 Système de points',
        value: [
          `▸ **1 invitation** acceptée = **1 génération** disponible`,
          `▸ **Booster** le serveur principal = **+${CFG.boostBonus} utilisations**`,
          `▸ Les points peuvent être attribués manuellement`,
        ].join('\n'),
        inline: false,
      },
      {
        name: '『🔗』 Serveur principal',
        value: `Rejoins le serveur officiel pour accéder au bot :\n${CFG.mainInvite}`,
        inline: false,
      },
    );

  if (owner) {
    embed.addFields({
      name: '『👑』 Commandes Owner',
      value: [
        '`+addpoints @user N` — Ajouter des points',
        '`+removepoints @user N` — Retirer des points',
        '`+resetuser @user` — Réinitialiser un compte',
        '`+forcegenerate [@user]` — Générer sans vérification',
      ].join('\n'),
      inline: false,
    });
  }

  embed.setFooter(FOOTER).setTimestamp();

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setLabel('Rejoindre le serveur').setStyle(ButtonStyle.Link).setURL(CFG.mainInvite).setEmoji('🔗'),
  );

  return message.reply({ embeds: [embed], components: [row] });
}

async function cmdPoints(message) {
  const u     = DB.ensure(message.author.id, message.author.username);
  const total = u.points + u.invite_credits;

  const embed = new EmbedBuilder()
    .setColor(total > 0 ? CFG.colors.success : CFG.colors.error)
    .setTitle('『📊』 Mes utilisations')
    .setDescription(`> Solde de **${message.author.username}**\n​`)
    .addFields(
      { name: '💰 Points offerts',     value: `\`\`\`${u.points}\`\`\``,         inline: true },
      { name: '🔗 Crédits invitation',  value: `\`\`\`${u.invite_credits}\`\`\``, inline: true },
      { name: '⚡ Total disponible',    value: `\`\`\`${total}\`\`\``,            inline: true },
      { name: '🏆 Générations réalisées', value: `\`\`\`${u.generations}\`\`\``, inline: true },
    )
    .setFooter(FOOTER)
    .setTimestamp();

  return message.reply({ embeds: [embed] });
}

async function cmdInvites(message) {
  const u = DB.ensure(message.author.id, message.author.username);

  const embed = new EmbedBuilder()
    .setColor(CFG.colors.accent)
    .setTitle('『🔗』 Mes invitations')
    .setDescription(
      `> Chaque membre que tu invites sur le serveur principal\n` +
      `> te crédite automatiquement **+1 génération**.\n​`
    )
    .addFields(
      { name: '🔗 Crédits invitation',  value: `\`\`\`${u.invite_credits}\`\`\``,                 inline: true },
      { name: '💰 Points bonus',         value: `\`\`\`${u.points}\`\`\``,                         inline: true },
      { name: '⚡ Total utilisations',   value: `\`\`\`${u.points + u.invite_credits}\`\`\``,      inline: true },
      {
        name: '💡 Comment gagner des utilisations ?',
        value: `▸ Invite des membres → ${CFG.mainInvite}\n▸ Boost le serveur principal → **+${CFG.boostBonus}** utilisations offertes`,
        inline: false,
      },
    )
    .setFooter(FOOTER)
    .setTimestamp();

  return message.reply({ embeds: [embed] });
}

async function cmdAddPoints(message, args) {
  const target = message.mentions.users.first();
  const amount = parseInt(args[1], 10);
  if (!target || isNaN(amount) || amount <= 0)
    return message.reply({ embeds: [E.err('Usage incorrect', '`+addpoints @utilisateur nombre`')] });

  DB.ensure(target.id, target.username);
  const u = DB.addPoints(target.id, amount);
  return message.reply({
    embeds: [E.ok('Points ajoutés', `**+${amount}** points ajoutés à ${target}\n\nNouveaux soldes : \`${u.points}\` pts · \`${u.invite_credits}\` crédits`)],
  });
}

async function cmdRemovePoints(message, args) {
  const target = message.mentions.users.first();
  const amount = parseInt(args[1], 10);
  if (!target || isNaN(amount) || amount <= 0)
    return message.reply({ embeds: [E.err('Usage incorrect', '`+removepoints @utilisateur nombre`')] });

  DB.ensure(target.id, target.username);
  const u = DB.removePoints(target.id, amount);
  return message.reply({
    embeds: [E.ok('Points retirés', `**-${amount}** points retirés à ${target}\n\nSolde : \`${u.points}\` points`)],
  });
}

async function cmdResetUser(message, args) {
  const target = message.mentions.users.first();
  if (!target)
    return message.reply({ embeds: [E.err('Usage incorrect', '`+resetuser @utilisateur`')] });

  const row = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId('reset_ok').setLabel('Confirmer').setStyle(ButtonStyle.Danger).setEmoji('🗑️'),
    new ButtonBuilder().setCustomId('reset_no').setLabel('Annuler').setStyle(ButtonStyle.Secondary),
  );

  const m = await message.reply({
    embeds: [E.warn('Confirmation requise', `Réinitialiser le compte de **${target.tag}** ?\n\nTous ses points, crédits et son historique seront effacés.`)],
    components: [row],
  });

  const i = await m.awaitMessageComponent({ filter: i => i.user.id === message.author.id, time: 15_000 }).catch(() => null);
  if (!i || i.customId === 'reset_no') return i?.update({ embeds: [E.info('Annulé', 'Réinitialisation annulée.')], components: [] });

  DB.ensure(target.id, target.username);
  DB.reset(target.id);
  return i.update({ embeds: [E.ok('Réinitialisé', `Le compte de **${target.tag}** a été remis à zéro.`)], components: [] });
}

async function cmdGenerate(message, args, client, forceTarget = null) {
  const userId = message.author.id;
  const owner  = isOwner(userId);
  const forced = forceTarget !== null;

  if (activeGen.has(userId))
    return message.reply({ embeds: [E.warn('En cours', 'Tu as déjà un questionnaire actif. Termine-le avant d\'en lancer un autre.')] });

  if (!forced) {
    if (!CFG.mainGuildId)
      return message.reply({ embeds: [E.err('Configuration manquante', 'Le bot n\'est pas encore configuré. Contacte l\'owner.')] });

    if (!owner) {
      const inGuild = await isInMainGuild(client, userId);
      if (!inGuild)
        return message.reply({ embeds: [E.err('Accès refusé', `Tu dois rejoindre le serveur principal pour utiliser cette commande :\n\n${CFG.mainInvite}`)] });
    }
  }

  if (!message.guild.members.me.permissions.has(PermissionFlagsBits.Administrator))
    return message.reply({ embeds: [E.err('Permissions insuffisantes', 'Le bot doit avoir la permission **Administrateur** sur ce serveur pour générer.')] });

  DB.ensure(userId, message.author.username);

  if (!forced && !owner && DB.totalUses(userId) <= 0)
    return message.reply({
      embeds: [E.err('Aucune utilisation disponible',
        `Tu n'as pas d'utilisation disponible.\n\n` +
        `▸ Invite des membres sur ${CFG.mainInvite} *(1 invitation = 1 génération)*\n` +
        `▸ Ou demande à l'owner de t'attribuer des points.`
      )],
    });

  activeGen.add(userId);
  let step = 0;

  try {
    if (forced && forceTarget) {
      await message.reply({ embeds: [E.premium('Force Generate', `Génération forcée pour **${forceTarget.tag}** — aucune déduction de points.`)] });
    }

    const result = await runQuestionnaire(message);
    if (!result) return;

    const { answers, qMsg } = result;

    if (!forced && !owner) DB.consume(userId);

    const targetId = forceTarget?.id ?? userId;

    const prog = async (txt) => {
      step++;
      await qMsg.edit({
        embeds: [E.load('Génération en cours...', `**Ne quitte pas le serveur.**\n\n\`\`\`\n${txt}\n\`\`\`\n*Étape ${step} / 5...*`)],
        components: [],
      }).catch(() => {});
    };

    const structure = await buildStructure(answers);
    const firstText = await applyStructure(message.guild, structure, prog);

    DB.recordGen(targetId, message.guild.id, answers.style, answers.name);

    const done = new EmbedBuilder()
      .setColor(CFG.colors.success)
      .setTitle('『✅』 Serveur généré avec succès !')
      .setDescription(
        `**${answers.name}** est maintenant prêt à accueillir ses membres !\n\n` +
        `> 🎮 Style : **${answers.style}**\n` +
        `> ✨ Finition : **${answers.finish}**\n` +
        `> 👤 Fondateur : **${answers.founder}**`
      )
      .setFooter(FOOTER)
      .setTimestamp();

    if (firstText) await firstText.send({ embeds: [done] }).catch(() => {});

    const target = forceTarget ?? message.author;
    await target.send({ embeds: [done] }).catch(() => {});

  } catch (err) {
    log.error('generate:', err);
    await message.channel.send({
      embeds: [E.err('Erreur de génération', `Une erreur est survenue.\n\`\`\`\n${err.message}\n\`\`\``)],
    }).catch(() => {});
  } finally {
    activeGen.delete(userId);
  }
}

async function cmdForceGenerate(message, args, client) {
  const target = message.mentions.users.first() || null;
  return cmdGenerate(message, args, client, target ?? message.author);
}

// ══════════════════════════════════════════════════════════
//  TABLE DE ROUTAGE DES COMMANDES
// ══════════════════════════════════════════════════════════

const COMMANDS = {
  help:          { fn: cmdHelp,          ownerOnly: false },
  points:        { fn: cmdPoints,        ownerOnly: false },
  invites:       { fn: cmdInvites,       ownerOnly: false },
  addpoints:     { fn: cmdAddPoints,     ownerOnly: true  },
  removepoints:  { fn: cmdRemovePoints,  ownerOnly: true  },
  resetuser:     { fn: cmdResetUser,     ownerOnly: true  },
  generate:      { fn: cmdGenerate,      ownerOnly: false },
  forcegenerate: { fn: cmdForceGenerate, ownerOnly: true  },
};

// ══════════════════════════════════════════════════════════
//  CLIENT DISCORD
// ══════════════════════════════════════════════════════════

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildInvites,
  ],
  partials: [Partials.Message, Partials.Channel, Partials.GuildMember],
});

const inviteCache = new Map(); // Map<guildId, Map<code, uses>>

// ── ready ──────────────────────────────────────────────────
client.once('ready', async () => {
  log.ok(`Connecté : ${client.user.tag}`);
  log.info(`Serveurs : ${client.guilds.cache.size}  |  Préfixe : ${CFG.prefix}`);
  log.info(`Owners   : ${OWNERS.join(', ')}`);

  client.user.setPresence({
    activities: [{ name: `${CFG.prefix}help • Generate`, type: ActivityType.Watching }],
    status: 'online',
  });

  if (CFG.mainGuildId) {
    const g = client.guilds.cache.get(CFG.mainGuildId);
    if (g) {
      const invs = await g.invites.fetch().catch(() => null);
      if (invs) {
        inviteCache.set(g.id, new Map(invs.map(i => [i.code, i.uses])));
        log.ok(`Cache invitations : ${invs.size} invitations chargées`);
      } else {
        log.warn('Impossible de charger les invitations (permission manquante ?)');
      }
    } else {
      log.warn('Serveur principal introuvable — vérifiez MAIN_GUILD_ID');
    }
  }
});

// ── messageCreate ──────────────────────────────────────────
client.on('messageCreate', async (message) => {
  if (message.author.bot) return;
  if (!message.content.startsWith(CFG.prefix)) return;

  const args = message.content.slice(CFG.prefix.length).trim().split(/\s+/);
  const name = args.shift().toLowerCase();

  const cmd = COMMANDS[name];
  if (!cmd) return;

  if (cmd.ownerOnly && !isOwner(message.author.id)) {
    return message.reply({ embeds: [E.err('Accès refusé', 'Cette commande est réservée aux owners du bot.')] });
  }

  if (!isOwner(message.author.id)) {
    const secs = CD[name] ?? 3;
    const rem  = checkCooldown(message.author.id, name, secs);
    if (rem > 0)
      return message.reply({ embeds: [E.warn('Cooldown', `Attends encore **${rem}s** avant de réutiliser \`${CFG.prefix}${name}\`.`)] });
  }

  try {
    await cmd.fn(message, args, client);
  } catch (err) {
    log.error(`+${name}:`, err);
    message.reply({ embeds: [E.err('Erreur interne', 'Une erreur inattendue s\'est produite.')] }).catch(() => {});
  }
});

// ── guildMemberAdd (suivi invitations) ─────────────────────
client.on('guildMemberAdd', async (member) => {
  if (member.guild.id !== CFG.mainGuildId) return;
  try {
    const cached = inviteCache.get(member.guild.id) ?? new Map();
    const fresh  = await member.guild.invites.fetch();
    const used   = fresh.find(inv => (cached.get(inv.code) ?? -1) < inv.uses);
    inviteCache.set(member.guild.id, new Map(fresh.map(i => [i.code, i.uses])));
    if (used?.inviter) {
      DB.ensure(used.inviter.id, used.inviter.username);
      DB.addCredits(used.inviter.id, 1);
      log.info(`+1 crédit invitation → ${used.inviter.tag} (${used.code})`);
    }
  } catch (err) {
    log.error('guildMemberAdd:', err.message);
  }
});

// ── inviteCreate / inviteDelete ────────────────────────────
client.on('inviteCreate', (invite) => {
  if (invite.guild?.id !== CFG.mainGuildId) return;
  const c = inviteCache.get(invite.guild.id) ?? new Map();
  c.set(invite.code, invite.uses ?? 0);
  inviteCache.set(invite.guild.id, c);
});

client.on('inviteDelete', (invite) => {
  if (invite.guild?.id !== CFG.mainGuildId) return;
  inviteCache.get(invite.guild.id)?.delete(invite.code);
});

// ══════════════════════════════════════════════════════════
//  ANTI-CRASH
// ══════════════════════════════════════════════════════════

process.on('unhandledRejection', (err) => log.error('unhandledRejection:', err));
process.on('uncaughtException',  (err) => log.error('uncaughtException:', err.message, '\n', err.stack));
process.on('SIGTERM', () => {
  log.info('SIGTERM — arrêt propre...');
  client.destroy();
  process.exit(0);
});

// ══════════════════════════════════════════════════════════
//  UTILITAIRES
// ══════════════════════════════════════════════════════════

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ══════════════════════════════════════════════════════════
//  CONNEXION
// ══════════════════════════════════════════════════════════

client.login(process.env.TOKEN).catch(err => {
  log.error('Connexion Discord échouée :', err.message);
  process.exit(1);
});
