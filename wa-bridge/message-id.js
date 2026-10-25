function stableMessageId(message) {
  const serialized = message.id?._serialized;
  if (typeof serialized === 'string' && serialized.trim()) return serialized;

  const providerId = message.id?.id;
  const chatId = message.from || message.id?.remote;
  if (typeof providerId !== 'string' || !providerId.trim() ||
      typeof chatId !== 'string' || !chatId.trim()) {
    throw new Error('WhatsApp message has no usable ID or chat ID');
  }

  const fallback = `wa:${chatId}:${providerId}`;
  if (fallback.length > 200) {
    throw new Error('WhatsApp message ID is longer than Kurippu supports');
  }
  return fallback;
}

module.exports = stableMessageId;
