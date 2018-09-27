import React from 'react';

export default class Provider extends React.Component {
  render() {
    return this.props.values.reduce(
      (inner, [context, value]) =>
        <context.Provider value={value}>{inner}</context.Provider>,
      this.props.children);
  }
}
