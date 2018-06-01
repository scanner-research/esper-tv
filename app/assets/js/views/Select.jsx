import React from 'react';
import Select2 from 'react-select2-wrapper';
import keyboardManager from 'utils/KeyboardManager.jsx';

export default class Select extends React.Component {
  componentDidMount() {
    keyboardManager.lock();
    this._n.el.select2('open');
  }

  componentWillUnmount() {
    keyboardManager.unlock();
  }

  render() {
    return <Select2
             ref={(n) => {this._n = n;}}
             data={this.props.data.map(([k, v]) => ({id: k, text: v}))}
             options={{placeholder: 'Search', width: this.props.width, closeOnSelect: false}}
             onSelect={(e) => {this.props.onSelect(e.target.value); e.preventDefault();}}
             onClose={(e) => {this.props.onClose(e);}} />;
  }
}
