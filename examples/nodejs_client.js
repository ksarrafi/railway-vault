/**
 * Railway Vault Node.js Client
 * 
 * Drop this file into your Node.js application and use it to fetch secrets.
 * 
 * Installation:
 *     npm install axios
 * 
 * Usage:
 *     const VaultClient = require('./vault_client');
 *     
 *     const vault = new VaultClient();
 *     const DATABASE_URL = await vault.get('myapp:database_url');
 *     const API_KEY = await vault.get('myapp:api_key');
 */

const axios = require('axios');

class VaultClient {
  /**
   * Initialize vault client.
   * 
   * @param {Object} options
   * @param {string} options.url - Vault URL (defaults to VAULT_URL env var)
   * @param {string} options.token - Auth token (defaults to VAULT_TOKEN env var)
   * @param {number} options.timeout - Request timeout in milliseconds
   */
  constructor(options = {}) {
    this.baseURL = options.url || process.env.VAULT_URL || 'http://vault.railway.internal:9999';
    this.token = options.token || process.env.VAULT_TOKEN;
    this.timeout = options.timeout || 5000;

    if (!this.token) {
      throw new Error('VAULT_TOKEN environment variable or token parameter required');
    }

    this.headers = {
      'Authorization': `Bearer ${this.token}`,
      'Content-Type': 'application/json'
    };

    this.client = axios.create({
      baseURL: this.baseURL,
      timeout: this.timeout,
      headers: this.headers
    });

    // Verify connection on init
    this.verifyConnection();
  }

  /**
   * Verify vault is accessible.
   */
  async verifyConnection() {
    try {
      const response = await axios.get(`${this.baseURL}/health`, {
        timeout: this.timeout
      });
      if (response.status !== 200) {
        throw new Error(`Vault health check failed: ${response.status}`);
      }
    } catch (error) {
      throw new Error(`Cannot connect to vault: ${error.message}`);
    }
  }

  /**
   * Get secret value from vault.
   * 
   * @param {string} key - Secret key (e.g., "myapp:database_url")
   * @returns {Promise<string>} Secret value
   * @throws {Error} If key not found or vault unreachable
   */
  async get(key) {
    try {
      const response = await this.client.get(`/get/${key}`);
      return response.data.value;
    } catch (error) {
      if (error.response && error.response.status === 404) {
        throw new Error(`Secret not found: ${key}`);
      }
      throw new Error(`Failed to get secret ${key}: ${error.message}`);
    }
  }

  /**
   * Store secret in vault.
   * 
   * @param {string} key - Secret key
   * @param {string} value - Secret value
   * @throws {Error} If vault unreachable
   */
  async set(key, value) {
    try {
      await this.client.post('/set', { key, value });
    } catch (error) {
      throw new Error(`Failed to set secret ${key}: ${error.message}`);
    }
  }

  /**
   * Delete secret from vault.
   * 
   * @param {string} key - Secret key to delete
   * @throws {Error} If vault unreachable
   */
  async delete(key) {
    try {
      await this.client.post(`/delete/${key}`);
    } catch (error) {
      throw new Error(`Failed to delete secret ${key}: ${error.message}`);
    }
  }

  /**
   * List all secret keys.
   * 
   * @returns {Promise<string[]>} List of secret keys
   * @throws {Error} If vault unreachable
   */
  async list() {
    try {
      const response = await this.client.get('/list');
      return response.data.keys;
    } catch (error) {
      throw new Error(`Failed to list secrets: ${error.message}`);
    }
  }

  /**
   * Check if secret exists.
   * 
   * @param {string} key - Secret key to check
   * @returns {Promise<boolean>} True if exists
   */
  async has(key) {
    try {
      const response = await this.client.get(`/has/${key}`);
      return response.data.exists;
    } catch (error) {
      return false;
    }
  }
}

/**
 * Load all secrets with optional prefix into an object.
 * 
 * @param {string} prefix - Optional key prefix filter (e.g., "myapp:")
 * @returns {Promise<Object>} Object of key-value pairs
 * 
 * Example:
 *     const secrets = await loadSecrets('myapp:');
 *     const DATABASE_URL = secrets['myapp:database_url'];
 */
async function loadSecrets(prefix = '') {
  const vault = new VaultClient();
  let keys = await vault.list();

  if (prefix) {
    keys = keys.filter(k => k.startsWith(prefix));
  }

  const secrets = {};
  for (const key of keys) {
    secrets[key] = await vault.get(key);
  }

  return secrets;
}

// Example usage
if (require.main === module) {
  (async () => {
    try {
      // Example 1: Basic usage
      const vault = new VaultClient();

      // Set a secret
      await vault.set('test:hello', 'world');
      console.log('✅ Secret set');

      // Get a secret
      const value = await vault.get('test:hello');
      console.log(`✅ Secret value: ${value}`);

      // List all secrets
      const keys = await vault.list();
      console.log(`✅ All keys: ${keys.join(', ')}`);

      // Check if exists
      const exists = await vault.has('test:hello');
      console.log(`✅ Exists: ${exists}`);

      // Delete secret
      await vault.delete('test:hello');
      console.log('✅ Secret deleted');

      console.log('\n✅ All operations successful!');

      // Example 2: Load all app secrets at startup
      console.log('\nLoading application secrets...');
      const appSecrets = await loadSecrets('myapp:');
      console.log(`✅ Loaded ${Object.keys(appSecrets).length} secrets for myapp`);

      // Use them
      // const DATABASE_URL = appSecrets['myapp:database_url'];
      // const API_KEY = appSecrets['myapp:api_key'];

    } catch (error) {
      console.error(`❌ Error: ${error.message}`);
      process.exit(1);
    }
  })();
}

module.exports = VaultClient;
module.exports.loadSecrets = loadSecrets;
