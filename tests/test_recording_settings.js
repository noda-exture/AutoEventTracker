const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { resolveRecordingViewport } = require('../recording_settings');

test('recorder uses config or explicit width and height', () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'aet-recording-'));
  const filename = path.join(folder, 'global_config.json');
  try {
    fs.writeFileSync(filename, JSON.stringify({ recording: { viewport: { width: 1440, height: 900 } } }));
    assert.deepEqual(resolveRecordingViewport(undefined, undefined, filename), {width: 1440, height: 900});
    assert.deepEqual(resolveRecordingViewport('1024', '768', filename), {width: 1024, height: 768});
    for (const args of [['0','800'], ['true','800'], ['1024',undefined], ['1024','16385']]) {
      assert.throws(() => resolveRecordingViewport(...args, filename));
    }
    fs.writeFileSync(filename, JSON.stringify({ recording: { viewport: {width: '1440', height: 900} } }));
    assert.throws(() => resolveRecordingViewport(undefined, undefined, filename));
  } finally {
    fs.rmSync(folder, {recursive: true, force: true});
  }
});
