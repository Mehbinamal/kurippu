const test = require('node:test');
const assert = require('node:assert/strict');
const stableMessageId = require('./message-id');

test('preserves WhatsApp serialized message IDs', () => {
  assert.equal(stableMessageId({
    from: '123@c.us',
    id: { _serialized: 'false_123@c.us_ABC', id: 'ABC' },
  }), 'false_123@c.us_ABC');
});

test('builds a stable ID for LID messages without a serialized ID', () => {
  const message = { from: '274246697775240@lid', id: { id: 'ABC' } };
  assert.equal(stableMessageId(message), 'wa:274246697775240@lid:ABC');
  assert.equal(stableMessageId(message), stableMessageId(message));
});

test('rejects messages without enough identity data', () => {
  assert.throws(() => stableMessageId({ from: '123@lid', id: {} }), /no usable ID/);
});
