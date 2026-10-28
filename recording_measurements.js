// Capture network packets without attributing them to recorded actions.
function measurementPacket(request, sequence) {
  const url = request.url();
  let type;
  if (url.includes('google-analytics.com/g/collect') || url.includes('google-analytics.com/collect')) {
    type = 'GA4';
  } else if (url.includes('/b/ss/') || url.includes('.2o7.net') || url.includes('.sc.omtrdc.net')) {
    type = 'Adobe Analytics (Legacy)';
  } else if (url.includes('edge.adobedc.net') && url.includes('/v1/')) {
    type = 'AEP Web SDK';
  } else {
    return null;
  }
  const method = request.method();
  const post_data = method === 'POST' ? request.postData() : null;
  const packet = { type, url, method, post_data, timestamp: Date.now() / 1000,
    capture_sequence: sequence };
  if (type === 'AEP Web SDK') {
    try { packet.xdm_payload = JSON.parse(post_data); }
    catch { packet.xdm_payload = post_data; }
  }
  return packet;
}

module.exports = { measurementPacket };
