const fs = require('fs');
const path = require('path');

function resolveRecordingViewport(width, height, configPath = path.join(__dirname, 'global_config.json')) {
  let viewport;
  if (width !== undefined || height !== undefined) {
    if (!/^\d+$/.test(width || '') || !/^\d+$/.test(height || '')) {
      throw new Error('記録サイズは幅・高さの両方を整数で指定してください。');
    }
    viewport = { width: Number(width), height: Number(height) };
  } else {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    viewport = config.recording === undefined
      ? config.devices?.[config.default_device]?.viewport
      : config.recording?.viewport;
  }
  if (!viewport || Object.keys(viewport).sort().join(',') !== 'height,width' ||
      ![viewport.width, viewport.height].every(value => Number.isInteger(value) && value >= 1 && value <= 16384)) {
    throw new Error('記録時のviewportはwidth・heightを1～16384の整数で指定してください。');
  }
  return { width: viewport.width, height: viewport.height };
}

module.exports = { resolveRecordingViewport };
