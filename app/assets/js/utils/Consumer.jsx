import React from 'react';
import {Observer} from 'mobx-react';

export default class Consumer extends React.Component {
  render() {
    let args = [];
    return this.props.contexts.reduce(
      (acc, ctx) => () => <ctx.Consumer>{ x => { args.unshift(x); return acc() }}</ctx.Consumer>,
      () => <Observer>{() => this.props.children(...args)}</Observer>)();
  }
}
