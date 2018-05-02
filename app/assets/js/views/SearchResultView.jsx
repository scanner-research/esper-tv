import React from 'react';
import * as Rb from 'react-bootstrap';
import {observer} from 'mobx-react';
import SidebarView from './SidebarView.jsx';
import ClipView from './ClipView.jsx';
import TimelineView from './TimelineView.jsx';
import axios from 'axios';

// Hack used to prevent typing into non-React elements (e.g. a select2 box) from triggering keyboard
// events on React elements (e.g. the clip viewer). This happens because React uses a synthetic event
// system separate from the one built-in to the DOM, so it's difficult to deal with the cross-system
// triggers. We use this global variable for any time when there should definitely be no keypress
// events happening EXCEPT on the element the user is currently typing into.
window.IGNORE_KEYPRESS = false;

// Displays results with basic pagination
@observer
class GroupsView extends React.Component {
  state = {
    page: 0,
    selected_start: -1,
    selected_end: -1,
    ignored: new Set(),
    positive_ex: new Set(),
    negative_ex: new Set()
  }

  _lastResult = window.search_result.result;

  constructor() {
    super();
    document.addEventListener('keypress', this._onKeyPress);
  }

  getColorClass(i){
    if (this.state.ignored.has(i)) {
      return 'ignored ';
    } else if (this.state.selected_start == i || (this.state.selected_start <= i && i <= this.state.selected_end)){
      return 'selected ';
    } else if (this.state.positive_ex.has(i)){
      return 'positive ';
    } else if (this.state.negative_ex.has(i)){
      return 'negative ';
    }
  }

  _onKeyPress = (e) => {
    if (IGNORE_KEYPRESS) {
      return;
    }

    let chr = String.fromCharCode(e.which);
    if (chr == 'a') {
      if (this.state.selected_start == -1) {
        return;
      }

      let green = this.state.positive_ex;

      let labeled = [];
      let end = this.state.selected_end == -1 ? this.state.selected_start : this.state.selected_end;
      for (let i = this.state.selected_start; i <= end; i++) {
        if (this.state.ignored.has(i)) {
          continue;
        }

        labeled.push(window.search_result.result[i]);
        green.add(i);
      }

      // TODO(wcrichto): make saving state + errors more apparent to user (without alert boxes)
      axios
        .post('/api/labeled', {dataset: DATASET, groups: labeled, label_mode: DISPLAY_OPTIONS.get('label_mode')})
        .then(((response) => {
          if (!response.data.success) {
            console.error(response.data.error);
            alert(response.data.error);
          } else {
            console.log('Done!');
            this.setState({
              positive_ex: green,
              selected_start: -1,
              selected_end: -1
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
    return Math.floor((window.search_result.result.length - 1)/ DISPLAY_OPTIONS.get('results_per_page'));
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
    if (window.search_result.result != this._lastResult) {
      this._lastResult = window.search_result.result;
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
      <div className='groups'>
        <div>
          {_.range(DISPLAY_OPTIONS.get('results_per_page') * this.state.page,
                   Math.min(DISPLAY_OPTIONS.get('results_per_page') * (this.state.page + 1),
                            window.search_result.result.length))
            .map((i) => <GroupView key={i} group={window.search_result.result[i]} group_id={i}
                                   onSelect={this._onSelect} onIgnore={this._onIgnore}
                                   colorClass={this.getColorClass(i)}/>)}
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
      </div>
    );
  }
}

@observer
class GroupView extends React.Component {
  state = {
    expand: false
  }

  _onKeyPress = (e) => {
    if (IGNORE_KEYPRESS) {
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
      <div className={'group ' + (this.props.colorClass || '')} onMouseEnter={this._onMouseEnter} onMouseLeave={this._onMouseLeave}>
        {DISPLAY_OPTIONS.get('timeline_view') && group.type == 'contiguous'
         ? <TimelineView group={group} expand={this.state.expand}/>
         : <div className={group.type}>
           <div className='group-label'>{group.label}</div>
           <div className='group-elements'>
             {group.elements.map((clip, i) =>
               <ClipView key={i} clip={clip} showMeta={true}
                         expand={this.state.expand} />)}
             <div className='clearfix' />
           </div>
         </div>}
      </div>
    );
  }
}

@observer
export default class SearchResultView extends React.Component {
  render() {
    return (
      <div className='search-results'>
        <SidebarView />
        <GroupsView />
      </div>
    )
  }
}
