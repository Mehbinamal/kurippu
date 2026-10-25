async function resolveChatId(client, chatId) {
  if (typeof chatId !== 'string' || !chatId.trim()) {
    throw new Error('WhatsApp recipient ID is missing');
  }
  if (!chatId.endsWith('@lid')) return chatId;

  if (typeof client.getContactLidAndPhone !== 'function') {
    throw new Error('This whatsapp-web.js version cannot resolve WhatsApp LID recipients');
  }

  const [contact] = await client.getContactLidAndPhone([chatId]);
  const phoneId = contact?.pn;
  if (typeof phoneId !== 'string' || !phoneId.endsWith('@c.us')) {
    throw new Error('Could not resolve this WhatsApp LID to a phone chat; update whatsapp-web.js and try again');
  }
  return phoneId;
}

module.exports = resolveChatId;
