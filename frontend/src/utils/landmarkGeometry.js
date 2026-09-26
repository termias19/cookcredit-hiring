// The overlay follows the uncropped video, including letterboxing. No scoring.
export function containedFrame(width, height, videoWidth, videoHeight) {
  if (![width, height, videoWidth, videoHeight].every(n => Number.isFinite(n) && n > 0)) return null
  const scale = Math.min(width / videoWidth, height / videoHeight)
  const w = videoWidth * scale, h = videoHeight * scale
  return { x: (width - w) / 2, y: (height - h) / 2, width: w, height: h }
}
export const HAND_EDGES = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]]
