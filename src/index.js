const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(process.cwd(), 'data');
const DB_FILE = path.join(DATA_DIR, 'database.json');

// ── Init fichier DB ───────────────────────────────────────
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
if (!fs.existsSync(DB_FILE)) fs.writeFileSync(DB_FILE, '{}', 'utf8');

function read() {
  try {
    return JSON.parse(fs.readFileSync(DB_FILE, 'utf8'));
  } catch {
    return {};
  }
}

function write(data) {
  fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2), 'utf8');
}

function get(key, defaultVal = null) {
  const data = read();
  return data[key] !== undefined ? data[key] : defaultVal;
}

function set(key, value) {
  const data = read();
  data[key] = value;
  write(data);
}

function del(key) {
  const data = read();
  delete data[key];
  write(data);
}

// ── API publique ──────────────────────────────────────────
module.exports = {
  async getPoints(userId) {
    return get(`points_${userId}`, 0);
  },
  async setPoints(userId, amount) {
    set(`points_${userId}`, amount);
  },
  async addPoints(userId, amount) {
    const current = get(`points_${userId}`, 0);
    set(`points_${userId}`, current + amount);
  },
  async removePoints(userId, amount) {
    const current = get(`points_${userId}`, 0);
    set(`points_${userId}`, Math.max(0, current - amount));
  },

  async getGenerations(userId) {
    return get(`generations_${userId}`, 0);
  },
  async incrementGenerations(userId) {
    const current = get(`generations_${userId}`, 0);
    set(`generations_${userId}`, current + 1);
  },

  async getInvites(userId) {
    return get(`invites_${userId}`, 0);
  },
  async setInvites(userId, amount) {
    set(`invites_${userId}`, amount);
  },
  async addInvites(userId, amount) {
    const current = get(`invites_${userId}`, 0);
    set(`invites_${userId}`, current + amount);
  },

  async getCooldown(userId, command) {
    return get(`cooldown_${command}_${userId}`, null);
  },
  async setCooldown(userId, command, timestamp) {
    set(`cooldown_${command}_${userId}`, timestamp);
  },

  async resetUser(userId) {
    del(`points_${userId}`);
    del(`invites_${userId}`);
    del(`generations_${userId}`);
  },

  async addHistory(userId, data) {
    const history = get(`history_${userId}`, []);
    history.push({ ...data, date: new Date().toISOString() });
    if (history.length > 20) history.shift();
    set(`history_${userId}`, history);
  },

  async hasReceivedBoosterBonus(userId) {
    return get(`boosterBonus_${userId}`, false);
  },
  async setBoosterBonus(userId) {
    set(`boosterBonus_${userId}`, true);
  },

  async getTotalGenerations() {
    return get('stats_totalGenerations', 0);
  },
  async incrementTotalGenerations() {
    const current = get('stats_totalGenerations', 0);
    set('stats_totalGenerations', current + 1);
  }
};
