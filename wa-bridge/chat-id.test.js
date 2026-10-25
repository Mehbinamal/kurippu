const test = require('node:test');
const assert = require('node:assert/strict');
const resolveChatId = require('./chat-id');

test('leaves phone-number WhatsApp IDs unchanged', async () => {
  const id = '919876543210@c.us';
  assert.equal(await resolveChatId({}, id), id);
});

test('resolves LID chats to their phone-number chat ID', async () => {
  const client = {
    getContactLidAndPhone: async ids => {
      assert.deepEqual(ids, ['274246697775240@lid']);
      return [{ lid: ids[0], pn: '919876543210@c.us' }];
    },
  };
  assert.equal(await resolveChatId(client, '274246697775240@lid'), '919876543210@c.us');
});

test('rejects unresolved LID chat IDs instead of attempting a send', async () => {
  const client = { getContactLidAndPhone: async () => [{ lid: '123@lid', pn: undefined }] };
  await assert.rejects(resolveChatId(client, '123@lid'), /Could not resolve/);
});

test('rejects missing chat IDs', async () => {
  await assert.rejects(resolveChatId({}, ''), /recipient ID is missing/);
});
