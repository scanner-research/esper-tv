import React from 'react';
import ReactSelect from 'react-select';
import keyboardManager from 'utils/KeyboardManager.jsx';

export default class Select extends React.Component {
  state = {
    value: null
  }

  componentDidMount() {
    keyboardManager.lock();
  }

  componentWillUnmount() {
    keyboardManager.unlock();
  }
  render() {
    return <ReactSelect.Creatable
             options={this.props.data.map(([k, v]) => ({value: k, label: v}))}
             multi={this.props.multi}
             placeholder={'Search...'}
             style={{width: this.props.width}}
             openOnFocus={true}
             autoFocus={true}
             value={this.state.value}
             escapeClearsValue={false}
             onInputKeyDown={(e) => {
                 if (e.which == 27) { // ESC
                   let v = this.state.value;
                   if (v === null || v === []) {
                     this.props.onClose();
                   } else {
                     this.props.onSelect(v);
                   }
                 }
             }}
             newOptionCreator={(opt) => { opt.valueKey = "-1"; return opt; }}
             onChange={(value) => { this.setState({value: value}); }} />;
  }
}
