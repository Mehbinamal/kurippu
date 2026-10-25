const path = require('path');
const crypto = require('crypto');
const stableMessageId = require('./message-id');
const resolveChatId = require('./chat-id');
const { applyMediaFix } = require('./media-workaround');

applyMediaFix(path.join(__dirname, 'node_modules', 'whatsapp-web.js'));

const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcodeTerminal = require('qrcode-terminal');
const express = require('express');

const KURIPPU_URL = process.env.KURIPPU_URL || 'http://127.0.0.1:8765';
const TOKEN = process.env.KURIPPU_WA_TOKEN;
const PORT = Number(process.env.WA_BRIDGE_PORT || 8766);
const noSandbox = process.env.WA_CHROME_NO_SANDBOX === '1';
if (!TOKEN) { console.error('Set KURIPPU_WA_TOKEN'); process.exit(1); }
if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) {
  console.error('WA_BRIDGE_PORT must be a valid TCP port');
  process.exit(1);
}
if (noSandbox) {
  console.warn('WARNING: Chromium sandbox is disabled. Only use this on a trusted, isolated computer.');
}

let latestQr = null;
let ready = false;

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: './.wwebjs_auth' }),
  puppeteer: {
    headless: true,
    args: noSandbox ? ['--no-sandbox', '--disable-setuid-sandbox'] : [],
  },
});

client.on('qr', qr => { latestQr = qr; ready = false; qrcodeTerminal.generate(qr, { small: true }); });
client.on('ready', () => { ready = true; latestQr = null; console.log('WhatsApp ready'); });
client.on('disconnected', reason => {
  ready = false;
  console.error('WhatsApp disconnected:', reason);
});

client.on('message', async msg => {
  try {
    if (msg.fromMe || msg.isStatus || msg.from.endsWith('@g.us')) return; // skip own, status, groups
    if (msg.type !== 'chat' || !msg.body.trim()) return;                  // text only for now

    const contact = await msg.getContact();
    const response = await fetch(`${KURIPPU_URL}/api/wa/incoming`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Kurippu-Token': TOKEN },
      body: JSON.stringify({
        msg_id: stableMessageId(msg),
        chat_id: msg.from,
        name: contact.pushname || contact.name || '',
        phone: contact.number || '',
        body: msg.body,
        ts: msg.timestamp,
      }),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(`Kurippu returned ${response.status}: ${detail}`);
    }
  } catch (e) { console.error('Could not forward incoming WhatsApp message:', e.message); }
});

const app = express();
app.use(express.json({ limit: '5mb' }));
function authorized(req) {
  const received = Buffer.from(req.get('X-Kurippu-Token') || '');
  const expected = Buffer.from(TOKEN);
  return received.length === expected.length && crypto.timingSafeEqual(received, expected);
}
app.use((req, res, next) =>
  authorized(req) ? next() : res.status(401).json({ error: 'Unauthorized' }));

app.get('/status', (_, res) => res.json({ ready, qr: latestQr }));

app.post('/send', async (req, res) => {
  const { chat_id, text, image_base64 } = req.body;
  if (typeof chat_id !== 'string' || !chat_id || typeof text !== 'string' || !text.trim()) {
    return res.status(400).json({ error: 'chat_id and text are required' });
  }
  if (!ready) return res.status(503).json({ error: 'not ready' });
  try {
    const chatId = await resolveChatId(client, chat_id);
    if (image_base64) {
      const media = new MessageMedia('image/png', image_base64, 'upi-qr.png');
      await client.sendMessage(chatId, media, { caption: text });
    } else {
      await client.sendMessage(chatId, text);
    }
    res.json({ ok: true });
  } catch (e) {
    console.error('WhatsApp send failed:', e.message);
    res.status(502).json({ error: `WhatsApp could not send the message: ${e.message}` });
  }
});

app.listen(PORT, '127.0.0.1', () => {
  console.log(`WhatsApp bridge listening on 127.0.0.1:${PORT}`);
  client.initialize();
});
