const axios = require('axios');
const aiClient = axios.create({ baseURL: process.env.FASTAPI_URL || 'http://127.0.0.1:8000' });

aiClient.interceptors.request.use((cfg) => {
  if (!cfg._userId) throw new Error('aiClient call missing user context');

  cfg.headers['X-User-Id'] = cfg._userId;
  return cfg;
});

module.exports = aiClient;
