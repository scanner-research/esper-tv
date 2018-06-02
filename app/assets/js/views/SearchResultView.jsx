import React from 'react';
import * as Rb from 'react-bootstrap';
import _ from 'lodash';
import {observer} from 'mobx-react';
import {observable, autorun, toJS} from 'mobx';
import {SidebarView, SELECT_MODES, LABEL_MODES} from './SidebarView.jsx';
import ClipView from './ClipView.jsx';
import TimelineView from './TimelineView.jsx';
import axios from 'axios';
import {BackendSettingsContext, SearchContext, FrontendSettingsContext, PythonContext} from './contexts.jsx';
import keyboardManager from 'utils/KeyboardManager.jsx';
import Consumer from 'utils/Consumer.jsx';

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
    let select_mode = this._frontendSettings.get('select_mode');
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

      let select_mode = this._frontendSettings.get('select_mode');
      if (select_mode == SELECT_MODES.RANGE) {
        let end = this.state.selected_end == -1 ? this.state.selected_start : this.state.selected_end;
        for (let i = this.state.selected_start; i <= end; i++) {
          if (this.state.ignored.has(i)) {
            continue;
          }

          labeled.push(this._searchResult.result[i]);
          green.add(i);
        }
      } else if (select_mode == SELECT_MODES.INDIVDIUAL) {
        for (let i of this.state.selected) {
          labeled.push(this._searchResult.result[i]);
          green.add(i);
        }
      }

      // TODO(wcrichto): make saving state + errors more apparent to user (without alert boxes)
      axios
        .post('/api/labeled', {groups: labeled, label_mode: this._frontendSettings.get('label_mode')})
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
    let select_mode = this._frontendSettings.get('select_mode');
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
    return Math.floor((this._searchResult.result.length - 1)/ this._frontendSettings.get('results_per_page'));
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
    if (this._searchResult != this._lastResult) {
      this._lastResult = this._searchResult;
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
      <Consumer contexts={[FrontendSettingsContext, SearchContext, PythonContext]}>{(frontendSettings, searchResult, python) => {
          this._searchResult = searchResult;
          this._python = python;
          this._frontendSettings = frontendSettings;
          return <div className='groups'>
            <div>
              {_.range(frontendSettings.get('results_per_page') * this.state.page,
                       Math.min(frontendSettings.get('results_per_page') * (this.state.page + 1),
                                this._searchResult.result.length))
                .map((i) => <GroupView key={i} group={this._searchResult.result[i]} group_id={i}
                                       onSelect={this._onSelect} onIgnore={this._onIgnore}
                                       colorClass={this._getColorClass(i)} />)}
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
      }}</Consumer>
    );
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

  _onMouseOver = () => {
    document.addEventListener('keypress', this._onKeyPress);
  }

  _onMouseOut = () => {
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
      <FrontendSettingsContext.Consumer>{frontendSettings =>
        <div className={'group ' + this.props.colorClass} onMouseOver={this._onMouseOver}
             onMouseOut={this._onMouseOut}>
          {this.props.colorClass != '' ? <div className={'select-overlay ' + this.props.colorClass} /> : <div />}
          {frontendSettings.get('timeline_view') && group.type == 'contiguous'
           ? <TimelineView group={group} expand={this.state.expand}  />
           : <div className={group.type}>
             {group.label && group.label !== ''
              ? <div className='group-label'>{group.label}</div>
              : <span />}
             <div className='group-elements'>
               {group.elements.map((clip, i) =>
                 <ClipView key={i} clip={clip} showMeta={true} expand={this.state.expand} />)}

               <div className='clearfix' />
             </div>
           </div>}
        </div>
      }</FrontendSettingsContext.Consumer>
    );
  }
}

@observer
export default class SearchResultView extends React.Component {
  state = {
    keyboardDisabled: false
  }

  _timer = null

  _onClick = () => {
    let disabled = !this.state.keyboardDisabled;

    // wcrichto 5-25-18: in order to disable the Jupyter keyboard manager, we have to call disable in an infinite
    // loop. This is because the ipywidgets framework uses KeyboardManager.register_events on the widget container
    // which can cause unpredictable behavior in unexpectedly reactivating the keyboard manager (hard to consistently
    // maintain focus on the widget area), so the simplest hacky solution is just to forcibly disable the manager
    // by overriding all other changes to its settings.
    if (disabled) {
      this._timer = setInterval(() => {this.props.jupyter.keyboard_manager.disable();}, 100);
    } else {
      clearInterval(this._timer);
      this.props.jupyter.keyboard_manager.enable();
    }
    this.setState({keyboardDisabled: disabled});
  }

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
      select_mode: SELECT_MODES.RANGE,
      subtitle_sidebar: true
    };

    if (_.size(this.props.settings) > 0) {
      console.log(this.props.settings);
      Object.assign(settings, this.props.settings);
    } else {
      let cached = localStorage.getItem('frontendSettings');
      if (cached !== null) {
        Object.assign(settings, JSON.parse(cached));
      }
    }

    this._settings = observable.map(settings);

    autorun(() => {
      localStorage.frontendSettings = JSON.stringify(toJS(this._settings));
    });
  }

  componentWillUnmount() {
    if (this._timer != null) {
      clearInterval(this._timer);
    }

    if (this.props.jupyter !== null) {
      this.props.jupyter.keyboard_manager.enable();
    }
  }

  render() {
    let hasJupyter = this.props.jupyter !== null;
    let JupyterButton = () => <button onClick={this._onClick}>{
        this.state.keyboardDisabled ? 'Enable Jupyter keyboard' : 'Disable Jupyter keyboard'
    }</button>;
    return (
      <FrontendSettingsContext.Provider value={this._settings}>
        <div className='search-results'>
          {hasJupyter ? <JupyterButton /> : <div />}
          <SidebarView {...this.props} />
          <GroupsView {...this.props} />
          {hasJupyter ? <JupyterButton /> : <div />}
        </div>
      </FrontendSettingsContext.Provider>
    )
  }
}
