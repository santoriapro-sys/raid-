'use strict';
require('dotenv').config();

const { Client, GatewayIntentBits, Partials } = require('discord.js');
const config = require('./config/config');
const logger = require('./utils/logger');

// ── Création du client ────────────────────────────────────
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.GuildInvites,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.DirectMessages,
    GatewayIntentBits.GuildMessageReactions
  ],
  partials: [Partials.Channel, Partials.Message, Partials.User]
});

// ── Chargement handlers ───────────────────────────────────
require('./handlers/commandHandler')(client);
require('./handlers/eventHandler')(client);

// ── Anti-crash système ────────────────────────────────────
process.on('unhandledRejection', (reason) => {
  logger.error(`Unhandled Rejection : ${reason?.stack || reason}`);
});

process.on('uncaughtException', (err) => {
  logger.error(`Uncaught Exception : ${err.stack}`);
  // On ne quitte PAS pour Railway (auto-restart si crash fatal)
});

process.on('uncaughtExceptionMonitor', (err) => {
  logger.error(`Exception Monitor : ${err.stack}`);
});

// ── Vérification token ────────────────────────────────────
if (!config.token) {
  logger.error('TOKEN manquant dans les variables d\'environnement');
  process.exit(1);
}

// ── Connexion Discord ─────────────────────────────────────
client.login(config.token).catch((err) => {
  logger.error(`Connexion échouée : ${err.message}`);
  process.exit(1);
});
