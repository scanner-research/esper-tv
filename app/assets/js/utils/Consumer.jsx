import React from 'react';

export default class Consumer extends React.Component {
  render() {
    let args = [];
    return this.props.contexts.reduce(
      (acc, ctx) => () => <ctx.Consumer>{ x => { args.unshift(x); return acc() }}</ctx.Consumer>,
      () => this.props.children(...args))();
  }
}
