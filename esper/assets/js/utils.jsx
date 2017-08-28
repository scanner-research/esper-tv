export function mediaUrl(path) {
  if (GOOGLE) {
    return 'http';
  } else {
    return 'fooey';
  }
}
