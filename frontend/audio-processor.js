/**
 * PCM AudioWorklet Processor
 * Converts Float32 audio samples to Int16 and sends via port message.
 * Used by GPU Live Mode to stream raw PCM to the backend WebSocket.
 */
class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input.length > 0 && input[0].length > 0) {
      const float32 = input[0];
      const int16 = new Int16Array(float32.length);
      for (let i = 0; i < float32.length; i++) {
        const s = Math.max(-1, Math.min(1, float32[i]));
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      this.port.postMessage(int16.buffer, [int16.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
