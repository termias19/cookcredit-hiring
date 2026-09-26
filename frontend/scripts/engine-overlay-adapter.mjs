// Adapt only the pinned published engine capture. Replay uses its renderer,
// not a second detector or a separately maintained knife-drawing algorithm.
function replaceOnce(source, before, after) {
  if (source.split(before).length !== 2) throw new Error('Published engine capture changed; review the overlay adapter')
  return source.replace(before, after)
}

export function captureFullOverlay(app, capture, rendererId) {
  if (!/^[a-f0-9]{64}$/.test(rendererId)) throw new Error('Missing pinned engine identity')
  app = replaceOnce(app, 'hiringLandmarks.add(originalLandmarkTime, knifeLm, otherLm)',
    'hiringLandmarks.add(originalLandmarkTime, knifeLm, otherLm, { width: state.canvas.width, height: state.canvas.height, bladeExtendK: state.bladeExtendK, knifePresent: state.knifePresent, knifeConf: state.knifeConf, knifeWorker: Boolean(state.knifeWorker), bladeTrail: state.bladeTrail.map(p => [Math.round(p.x * 100) / 100, Math.round(p.y * 100) / 100]) })')
  capture = replaceOnce(capture, 'add(mediaTime, knife, other)', 'add(mediaTime, knife, other, visual)')
  capture = replaceOnce(capture, 'frames.push([t, points(knife), points(other)])', 'frames.push([t, points(knife), points(other), visual])')
  capture = replaceOnce(capture, 'version: 1', `version: 2, renderer: '${rendererId}'`)
  return { app, capture }
}

export function originalEngineRenderer(source) {
  const names = ['drawOverlay', 'drawBlade', 'drawBladeFlow', 'drawKnifeBadge', 'drawHand']
  const functions = names.map(name => {
    const start = source.indexOf(`function ${name}(`)
    if (start < 0) throw new Error('Missing published engine renderer: ' + name)
    // These published functions close at column zero. Nested blocks are indented.
    const end = source.indexOf('\n}', start)
    if (end < 0) throw new Error('Invalid engine renderer: ' + name)
    return source.slice(start, end + 2)
  }).join('\n')
  const connections = source.match(/const HAND_CONNECTIONS = \[[\s\S]*?\n\];/)
  if (!connections) throw new Error('Missing engine hand connections')
  return `// Generated from the pinned CookCredit Engine renderer; no inference.\n${connections[0]}\nconst WRIST=0, INDEX_MCP=5;\nexport function drawOriginalEngineOverlay(ctx,row) {\nconst visual=row[3];\nconst state={...visual,ctx,canvas:{width:visual.width,height:visual.height},mode:'test',bladeTrail:visual.bladeTrail.map(([x,y])=>({x,y}))};\nconst hand=points=>points?.map(([x,y])=>({x,y}));\ndrawOverlay(hand(row[1]),hand(row[2]));\n${functions}\n}\n`
}
