/**
 * Audio utility functions for gpt-realtime voice integration
 *
 * gpt-realtime requires PCM16 format:
 * - 16-bit signed integers
 * - Little-endian byte order
 * - 24000 Hz sample rate
 * - Mono channel
 */

export const VOICE_SAMPLE_RATE = 24000

export function pcm16ToFloat32(base64: string): Float32Array {
  const binaryString = atob(base64)
  const bytes = new Uint8Array(binaryString.length)
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i)
  }

  const int16 = new Int16Array(bytes.buffer)

  const float32 = new Float32Array(int16.length)
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768
  }

  return float32
}

export function float32ToPcm16Base64(float32: Float32Array): string {
  const int16 = new Int16Array(float32.length)
  for (let i = 0; i < float32.length; i++) {
    const clamped = Math.max(-1, Math.min(1, float32[i]))
    int16[i] = clamped < 0 ? clamped * 32768 : clamped * 32767
  }

  const bytes = new Uint8Array(int16.buffer)

  let binaryString = ''
  for (let i = 0; i < bytes.length; i++) {
    binaryString += String.fromCharCode(bytes[i])
  }

  return btoa(binaryString)
}
