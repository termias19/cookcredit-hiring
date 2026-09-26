export function payRangeError(minimum, maximum) {
  if (minimum === '' || maximum === '') return ''
  const values = [Number(minimum), Number(maximum)]
  if (values.some(value => !Number.isInteger(value) || value < 0 || value > 10000)) {
    return 'Enter whole hourly amounts between 0 and 10,000.'
  }
  return values[0] > values[1] ? 'Pay minimum cannot exceed pay maximum.' : ''
}
