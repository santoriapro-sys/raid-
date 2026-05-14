'use strict';
require('dotenv').config();

const { Client, GatewayIntentBits, Partials } = require('discord.js');

console.log('=== START ===');
console.log('TOKEN:', process.env.TOKEN ? 'OK' : 'MANQUANT');

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.DirectMessages
  ],
  partials: [Partials.Channel, Partials.Message]
});

client.once('ready', () => {
  console.log(`✅ Bot connecté : ${client.user.tag}`);
  client.user.setActivity('+help | Generate', { type: 0 });
});

process.on('unhandledRejection', err => console.error('Rejection:', err));
process.on('uncaughtException', err => console.error('Exception:', err));

if (!process.env.TOKEN) {
  console.error('❌ TOKEN manquant');
  process.exit(1);
}

client.login(process.env.TOKEN)
  .then(() => console.log('✅ Login OK'))
  .catch(err => {
    console.error('❌ Login failed:', err.message);
    process.exit(1);
  });
