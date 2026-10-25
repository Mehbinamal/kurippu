const test = require('node:test');
const assert = require('node:assert/strict');
const { patchSource } = require('./media-workaround');

const messageObject = `        const message = {
            ...options,
            id: newMsgKey,
            ...mediaOptions,
        };

        // Bot's won't reply if canonicalUrl is set (linking)`;

test('removes the media model ID after constructing the outgoing message', () => {
  const patched = patchSource(messageObject);
  assert.match(patched, /id: newMsgKey,[\s\S]*\.\.\.mediaOptions/);
  assert.match(patched, /if \(message\.__x_id\) \{\s*delete message\.__x_id;\s*\}/);
});

test('does not apply the workaround more than once', () => {
  const patched = patchSource(messageObject);
  assert.equal(patchSource(patched), patched);
});

test('fails clearly when upstream changes the expected source shape', () => {
  assert.throws(() => patchSource('different source'), /Unrecognized whatsapp-web\.js Utils\.js/);
});
