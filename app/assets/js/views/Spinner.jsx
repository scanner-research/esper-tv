import React from 'react';

export default function spinner () {
  return (
    <img src={`${window.location.protocol}//${window.location.hostname}/static/images/spinner.gif`} />
  );
}
