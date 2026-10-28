const test = require('node:test');
const assert = require('node:assert/strict');
const { measurementPacket } = require('../recording_measurements');
const req = (url, body = null) => ({ url: () => url, method: () => body === null ? 'GET' : 'POST', postData: () => body });
test('captures raw analytics packets without step attribution', () => {
  for (const [url, type, body] of [
    ['https://www.google-analytics.com/g/collect?tid=G-T', 'GA4', 'en=first\nen=second'],
    ['https://example.sc.omtrdc.net/b/ss/test', 'Adobe Analytics (Legacy)', 'events=event1&v1=a&v1=b'],
    ['https://edge.adobedc.net/ee/v1/interact', 'AEP Web SDK', '{"events":[{"xdm":{}}]}'],
  ]) {
    const packet = measurementPacket(req(url, body), 3);
    assert.equal(packet.type, type);
    assert.equal(packet.post_data, body);
    assert.equal(packet.capture_sequence, 3);
    assert.equal(packet.step_id, undefined);
    if (type === 'AEP Web SDK') assert.deepEqual(packet.xdm_payload, JSON.parse(body));
  }
  assert.equal(measurementPacket(req('https://example.com/image.png'), 1), null);
  assert.equal(measurementPacket(req('https://edge.adobedc.net/ee/v1/interact', 'invalid'), 1).xdm_payload, 'invalid');
});

test('real recorder saves measurements beside the scenario', async () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const path = require('node:path');
  const http = require('node:http');
  const { spawn } = require('node:child_process');
  const root = path.resolve(__dirname, '..');
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'aet-recording-test-'));
  const server = http.createServer((req, res) => {
    res.setHeader('Content-Type', 'text/html');
    res.end(req.url === '/' ? `<div id="trigger">Hover</div><button id="choose" onclick="fetch('/google-analytics.com/g/collect?en=recorded_click&tid=G-T')">Click</button>` : 'OK');
  });
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const child = spawn(process.execPath, ['--require', path.join(root, 'packaging/recorder-smoke-preload.cjs'),
      path.join(root, 'record.js'), 'test', 'recorded', `http://127.0.0.1:${server.address().port}/`],
      { cwd: root, env: { ...process.env, AET_DATA_DIR: temp }, timeout: 30000 });
    let output = '';
    child.stdout.on('data', data => { output += data; });
    child.stderr.on('data', data => { output += data; });
    const code = await new Promise((resolve, reject) => { child.on('error', reject); child.on('close', resolve); });
    assert.equal(code, 0, output);
    const folder = path.join(temp, 'project/test/scenario/recorded');
    const scenario = JSON.parse(fs.readFileSync(path.join(folder, 'recorded.json')));
    assert.ok(scenario.steps.some(step => step.action === 'click'));
    const files = fs.readdirSync(folder).filter(file => file.includes('_recording_'));
    assert.equal(files.length, 1);
    const captured = JSON.parse(fs.readFileSync(path.join(folder, files[0])));
    assert.equal(captured.capture_source, 'recording');
    assert.equal(captured.events.length, 1);
    assert.ok(captured.events[0].url.includes('en=recorded_click'));
    assert.equal(captured.events[0].step_id, undefined);
  } finally {
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
