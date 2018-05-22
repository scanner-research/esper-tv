import React from 'react';
import * as Rb from 'react-bootstrap';
import {observer} from 'mobx-react';
import {observable, autorun, toJS} from 'mobx';
import {SidebarView, SELECT_MODES, LABEL_MODES} from './SidebarView.jsx';
import ClipView from './ClipView.jsx';
import TimelineView from './TimelineView.jsx';
import axios from 'axios';
import {GlobalContext, SearchContext, SettingsContext, PythonContext} from './contexts.jsx';
import keyboardManager from 'utils/KeyboardManager.jsx';
import _ from 'lodash';

// Displays results with basic pagination
@observer
class GroupsView extends React.Component {
  state = {
    page: 0,
    selected_start: -1,
    selected_end: -1,
    selected: new Set(),
    ignored: new Set(),
    positive_ex: new Set(),
    negative_ex: new Set()
  }

  constructor() {
    super();
    document.addEventListener('keypress', this._onKeyPress);
  }

  _isSelected = (i) => {
    let select_mode = this._displayOptions.get('select_mode');
    return (select_mode == SELECT_MODES.RANGE &&
            (this.state.selected_start == i ||
             (this.state.selected_start <= i && i <= this.state.selected_end))) ||
           (select_mode == SELECT_MODES.INDIVIDUAL && this.state.selected.has(i));
  }

  _getColorClass = (i) => {
    if (this.state.ignored.has(i)) {
      return 'ignored ';
    } else if (this._isSelected(i)) {
      return 'selected ';
    } else if (this.state.positive_ex.has(i)){
      return 'positive ';
    } else if (this.state.negative_ex.has(i)){
      return 'negative ';
    }
    return '';
  }

  _onKeyPress = (e) => {
    if (keyboardManager.locked()) {
      return;
    }

    let chr = String.fromCharCode(e.which);
    if (chr == 'a') {
      if (this.state.selected_start == -1) {
        return;
      }

      let green = this.state.positive_ex;
      let labeled = [];

      let select_mode = this._displayOptions.get('select_mode');
      if (select_mode == SELECT_MODES.RANGE) {
        let end = this.state.selected_end == -1 ? this.state.selected_start : this.state.selected_end;
        for (let i = this.state.selected_start; i <= end; i++) {
          if (this.state.ignored.has(i)) {
            continue;
          }

          labeled.push(this.props.searchResult.result[i]);
          green.add(i);
        }
      } else if (select_mode == SELECT_MODES.INDIVDIUAL) {
        for (let i of this.state.selected) {
          labeled.push(this.props.searchResult.result[i]);
          green.add(i);
        }
      }

      // TODO(wcrichto): make saving state + errors more apparent to user (without alert boxes)
      axios
        .post('/api/labeled', {dataset: DATASET, groups: labeled, label_mode: this._displayOptions.get('label_mode')})
        .then(((response) => {
          if (!response.data.success) {
            console.error(response.data.error);
            alert(response.data.error);
          } else {
            console.log('Done!');
            this.setState({
              positive_ex: green,
              selected_start: -1,
              selected_end: -1,
              selected: new Set()
            });
          }
        }).bind(this))
        .catch((error) => {
          console.error(error);
          alert(error);
        });
    }
  }

  _onSelect = (e) => {
    let select_mode = this._displayOptions.get('select_mode');
    if (select_mode == SELECT_MODES.RANGE) {
      if (this.state.selected_start == -1){
        this.setState({
          selected_start: e
        });
      } else if (e == this.state.selected_start) {
        this.setState({
          selected_start: -1,
          selected_end: -1
        });
      } else {
        if (e < this.state.selected_start) {
          if (this.state.selected_end == -1) {
            this.setState({
              selected_end: this.state.selected_start
            });
          }
          this.setState({
            selected_start: e
          });
        } else {
          this.setState({
            selected_end: e
          });
        }
      }
    } else if (select_mode == SELECT_MODES.INDIVIDUAL) {
      if (this.state.selected.has(e)) {
        this.state.selected.delete(e);
      } else {
        this.state.selected.add(e);
      }

      // Nested collection update, have to force re-render
      this.forceUpdate();
    }

    if (this._python) {
      this._python.update({selected: Array.from(this.state.selected)});
    }
  }

  _onIgnore = (e) => {
    if (this.state.ignored.has(e)) {
      this.state.ignored.delete(e);
    } else {
      this.state.ignored.add(e);
    }
    this.forceUpdate();
  }

  _numPages = () => {
    return Math.floor((this.props.searchResult.result.length - 1)/ this._displayOptions.get('results_per_page'));
  }

  _prevPage = (e) => {
    e.preventDefault();
    this.setState({page: Math.max(this.state.page - 1, 0)});
  }

  _nextPage = (e) => {
    e.preventDefault();
    this.setState({page: Math.min(this.state.page + 1, this._numPages())});
  }

  componentDidUpdate() {
    if (this.props.searchResult != this._lastResult) {
      this._lastResult = this.props.searchResult;
      this.setState({
        page: 0,
        positive_ex: new Set(),
        negative_ex: new Set(),
        ignored: new Set(),
        selected_start: -1,
        selected_end: -1
      });
    }
  }

  render () {
    return (
      <PythonContext.Consumer>{python => {
        this._python = python;
        return <SettingsContext.Consumer>{displayOptions => {
            this._displayOptions = displayOptions;
            return <div className='groups'>
              <div>
                {_.range(displayOptions.get('results_per_page') * this.state.page,
                         Math.min(displayOptions.get('results_per_page') * (this.state.page + 1),
                                  this.props.searchResult.result.length))
                  .map((i) => <GroupView key={i} group={this.props.searchResult.result[i]} group_id={i}
                                         onSelect={this._onSelect} onIgnore={this._onIgnore}
                                         colorClass={this._getColorClass(i)}
                                         searchResult={this.props.searchResult} />)}
                <div className='clearfix' />
              </div>
              <div className='page-buttons'>
                <Rb.ButtonGroup>
                  <Rb.Button onClick={this._prevPage}>&larr;</Rb.Button>
                  <Rb.Button onClick={this._nextPage}>&rarr;</Rb.Button>
                  <span key={this.state.page}>
                    <Rb.FormControl type="text" defaultValue={this.state.page + 1} onKeyPress={(e) => {
                        if (e.key === 'Enter') { this.setState({
                          page: Math.min(Math.max(parseInt(e.target.value)-1, 0), this._numPages())
                        }); }
                    }} />
                  </span>
                  <span className='page-count'>/ {this._numPages() + 1}</span>
                </Rb.ButtonGroup>
              </div>
            </div>;
        }}</SettingsContext.Consumer>
      }}</PythonContext.Consumer>);
  }
}

@observer
class GroupView extends React.Component {
  state = {
    expand: false
  }

  _onKeyPress = (e) => {
    if (keyboardManager.locked()) {
      return;
    }

    let chr = String.fromCharCode(e.which);
    if (chr == 'f') {
      this.setState({expand: !this.state.expand});
    } else if (chr == 's') {
      this.props.onSelect(this.props.group_id);
    } else if (chr == 'x') {
      this.props.onIgnore(this.props.group_id);
    }
  }

  _onMouseEnter = () => {
    document.addEventListener('keypress', this._onKeyPress);
  }

  _onMouseLeave = () => {
    document.removeEventListener('keypress', this._onKeyPress);
  }

  componentWillUnmount() {
    document.removeEventListener('keypress', this._onKeyPress);
  }

  componentWillReceiveProps(props) {
    if (this.props.group != props.group) {
      this.setState({expand: false});
    }
  }

  render () {
    let group = this.props.group;
    return (
      <SettingsContext.Consumer>{displayOptions =>
        <div className={'group ' + this.props.colorClass} onMouseEnter={this._onMouseEnter}
             onMouseLeave={this._onMouseLeave}>
          {this.props.colorClass != '' ? <div className={'select-overlay ' + this.props.colorClass} /> : <div />}
          {displayOptions.get('timeline_view') && group.type == 'contiguous'
           ? <TimelineView group={group} expand={this.state.expand} searchResult={this.props.searchResult} />
           : <div className={group.type}>
             {group.label && group.label !== ''
              ? <div className='group-label'>{group.label}</div>
              : <span />}
             <div className='group-elements'>
               {group.elements.map((clip, i) =>
                 <ClipView key={i} clip={clip} showMeta={true} expand={this.state.expand}
                           searchResult={this.props.searchResult} />)}

               <div className='clearfix' />
             </div>
           </div>}
        </div>
      }</SettingsContext.Consumer>
    );
  }
}

class JupyterButton extends React.Component {
  state = {
    keyboardDisabled: false
  }

  _timer = null

  _onClick = () => {
    let disabled = !this.state.keyboardDisabled;
    if (disabled) {
      this._timer = setInterval(() => {this.props.jupyter.keyboard_manager.disable();}, 100);
    } else {
      clearInterval(this._timer);
      this.props.jupyter.keyboard_manager.enable();
    }
    this.setState({keyboardDisabled: disabled});
  }

  componentWillUnmount() {
    clearInterval(this._timer);
    this.props.jupyter.keyboard_manager.enable();
  }

  render() {
    return (
      <button onClick={this._onClick}>{
        this.state.keyboardDisabled ? 'Enable Jupyter keyboard' : 'Disable Jupyter keyboard'
      }</button>
    );
  }
}

@observer
export default class SearchResultView extends React.Component {
  componentWillMount() {
    let settings = {
      results_per_page: 50,
      annotation_opacity: 1.0,
      show_pose: true,
      show_face: true,
      show_hands: true,
      show_lr: false,
      crop_bboxes: false,
      playback_speed: 1.0,
      show_middle_frame: true,
      show_gender_as_border: true,
      show_inline_metadata: false,
      thumbnail_size: 1,
      timeline_view: true,
      timeline_range: 20,
      track_color_identity: false,
      label_mode: LABEL_MODES.DEFAULT,
      select_mode: SELECT_MODES.RANGE
    };

    if (_.size(this.props.settings) > 0) {
      console.log(this.props.settings);
      Object.assign(settings, this.props.settings);
    } else {
      let cached = localStorage.getItem('displayOptions');
      if (cached !== null) {
        Object.assign(settings, JSON.parse(cached));
      }
    }

    this._settings = observable.map(settings);

    autorun(() => {
      localStorage.displayOptions = JSON.stringify(toJS(this._settings));
    });
  }

  render() {
    let hasJupyter = this.props.jupyter !== null;
    return (
      <SettingsContext.Provider value={this._settings}>
        <SearchContext.Provider value={this.props.searchResult}>
          <GlobalContext.Provider value={this.props.globals}>
            <div className='search-results'>
              {hasJupyter ? <JupyterButton {...this.props} /> : <div />}
              <SidebarView {...this.props} />
              <GroupsView {...this.props} />
            </div>
          </GlobalContext.Provider>
        </SearchContext.Provider>
      </SettingsContext.Provider>
    )
  }
}
