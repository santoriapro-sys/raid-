const Enmap = require('enmap');

const db = new Enmap({ name: 'generate', dataDir: './data' });

module.exports = {
  async getPoints(userId) {
    return db.ensure(`points_${userId}`, 0);
  },
  async setPoints(userId, amount) {
    db.set(`points_${userId}`, amount);
  },
  async addPoints(userId, amount) {
    const current = db.ensure(`points_${userId}`, 0);
    db.set(`points_${userId}`, current + amount);
  },
  async removePoints(userId, amount) {
    const current = db.ensure(`points_${userId}`, 0);
    db.set(`points_${userId}`, Math.max(0, current - amount));
  },

  async getGenerations(userId) {
    return db.ensure(`generations_${userId}`, 0);
  },
  async incrementGenerations(userId) {
    const current = db.ensure(`generations_${userId}`, 0);
    db.set(`generations_${userId}`, current + 1);
  },

  async getInvites(userId) {
    return db.ensure(`invites_${userId}`, 0);
  },
  async setInvites(userId, amount) {
    db.set(`invites_${userId}`, amount);
  },
  async addInvites(userId, amount) {
    const current = db.ensure(`invites_${userId}`, 0);
    db.set(`invites_${userId}`, current + amount);
  },

  async getCooldown(userId, command) {
    return db.get(`cooldown_${command}_${userId}`) || null;
  },
  async setCooldown(userId, command, timestamp) {
    db.set(`cooldown_${command}_${userId}`, timestamp);
  },

  async resetUser(userId) {
    db.delete(`points_${userId}`);
    db.delete(`invites_${userId}`);
    db.delete(`generations_${userId}`);
  },

  async addHistory(userId, data) {
    const history = db.ensure(`history_${userId}`, []);
    history.push({ ...data, date: new Date().toISOString() });
    if (history.length > 20) history.shift();
    db.set(`history_${userId}`, history);
  },

  async hasReceivedBoosterBonus(userId) {
    return db.ensure(`boosterBonus_${userId}`, false);
  },
  async setBoosterBonus(userId) {
    db.set(`boosterBonus_${userId}`, true);
  },

  async getTotalGenerations() {
    return db.ensure('stats_totalGenerations', 0);
  },
  async incrementTotalGenerations() {
    const current = db.ensure('stats_totalGenerations', 0);
    db.set('stats_totalGenerations', current + 1);
  }
};
