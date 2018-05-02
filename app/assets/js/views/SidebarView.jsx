import React from 'react';
import {observable, autorun, toJS} from 'mobx';
import {observer} from 'mobx-react';
import * as Rb from 'react-bootstrap';
import _ from 'lodash';

let LABEL_MODES = Object.freeze({
  DEFAULT: 0,
  SINGLE_IDENTITY: 1,
});

let labelModeToString = (i) => {
  if (i == LABEL_MODES.DEFAULT) {
    return "default";
  } else if (i == LABEL_MODES.SINGLE_IDENTITY) {
    return "single identity";
  } else if (i == LABEL_MODES.SINGLE_IDENTITY_BULK) {
    return "single identity (bulk)";
  } else {
    throw "Invalid label mode " + i;
  }
};

let displayOptions = JSON.parse(localStorage.getItem("displayOptions") || JSON.stringify({
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
  label_mode: LABEL_MODES.DEFAULT
}));

window.DISPLAY_OPTIONS = observable.map(displayOptions);

autorun(() => {
  localStorage.displayOptions = JSON.stringify(toJS(window.DISPLAY_OPTIONS));
});

@observer
class OptionsView extends React.Component {
  fields = [
    {
      name: 'Label mode',
      key: 'label_mode',
      type: 'option',
      opts: {
        keys: _.values(LABEL_MODES),
        values: _.values(LABEL_MODES).map((i) => labelModeToString(i))
      }
    },
    {
      name: 'Results per page',
      key: 'results_per_page',
      type: 'range',
      opts: {
        step: 1,
        min: 1,
        max: 500
      }
    },
    {
      name: 'Playback speed',
      key: 'playback_speed',
      type: 'range',
      opts: {
        min: 0,
        max: 6,
        step: 0.1
      },
    },
    {
      name: 'Annotation opacity',
      key: 'annotation_opacity',
      type: 'range',
      filter: (g) => g.elements[0].objects,
      opts: {
        min: 0,
        max: 1,
        step: 0.1
      },
    },
    {
      name: 'Thumbnail size',
      key: 'thumbnail_size',
      type: 'range',
      opts: {
        min: 1,
        max: 3,
        step: 1
      },
    },
    {
      name: 'Timeline range (s)',
      key: 'timeline_range',
      type: 'range',
      filter: (g) => g.type == 'contiguous',
      opts: {
        min: 1,
        max: 300,
        step: 1,
        disable_autoupdate: true
      },
    },
    {
      name: 'Crop bboxes',
      key: 'crop_bboxes',
      type: 'radio',
      filter: (g) => g.elements[0].objects,
    },
    {
      name: 'Show gender as border',
      key: 'show_gender_as_border',
      type: 'radio',
      filter: (g) => g.elements[0].objects && g.elements[0].objects[0].gender_id
    },
    {
      name: 'Show inline metadata',
      key: 'show_inline_metadata',
      type: 'radio'
    },
    {
      name: 'Show hands',
      key: 'show_hands',
      type: 'radio',
      filter: (g) => g.elements[0].objects && g.elements[0].objects[0].type == 'pose'
    },
    {
      name: 'Show pose',
      key: 'show_pose',
      type: 'radio',
      filter: (g) => g.elements[0].objects && g.elements[0].objects[0].type == 'pose'
    },
    {
      name: 'Show face',
      key: 'show_face',
      type: 'radio',
      filter: (g) => g.elements[0].objects && g.elements[0].objects[0].type == 'pose'
    },
    {
      name: 'Show left/right (blue/red)',
      key: 'show_lr',
      type: 'radio',
      filter: (g) => g.elements[0].objects && g.elements[0].objects[0].type == 'pose'
    },
    {
      name: 'Show middle frame',
      key: 'show_middle_frame',
      type: 'radio',
      filter: (g) => g.elements[0].max_frame !== undefined
    },
    {
      name: 'Color tracks by identity',
      key: 'track_color_identity',
      type: 'radio',
      filter: (g) => g.type == 'contiguous'
    },
  ]

  render() {
    return <div className='options'>
      <h2>Options</h2>
      <form>
        {this.fields.map((field, i) =>
          !field.filter || field.filter(window.search_result.result[0])
          ?  <Rb.FormGroup key={i}>
             <Rb.ControlLabel>{field.name}</Rb.ControlLabel>
             {{
                range: () => (
                  <span>
                    <input type="range" min={field.opts.min} max={field.opts.max}
                           step={field.opts.step} value={DISPLAY_OPTIONS.get(field.key)}
                           onChange={(e) => {
                               if (!field.opts.disable_autoupdate) {
                                 DISPLAY_OPTIONS.set(field.key, e.target.value)
                               }
                           }}/>
                    {/*
                        Using the field value as a key on its container allows the field to be editable by the user
                        while still permitting programmatic modification of the value (e.g. typing into a numeric
                        field vs. moving a slider). See:
                        https://stackoverflow.com/questions/30727837/react-change-input-defaultvalue-by-passing-props--
                     */}
                    <span key={DISPLAY_OPTIONS.get(field.key)}>
                      <Rb.FormControl type="number" min={field.opts.min} max={field.opts.max}
                                      defaultValue={DISPLAY_OPTIONS.get(field.key)}
                                      onKeyPress={(e) => {
                                          if (e.key === 'Enter') {
                                            DISPLAY_OPTIONS.set(field.key, e.target.value);
                                          }
                                      }} />
                    </span>
                  </span>),
                radio: () => (
                  <Rb.ButtonToolbar>
                    <Rb.ToggleButtonGroup type="radio" name={field.key} defaultValue={DISPLAY_OPTIONS.get(field.key)}
                                          onChange={(e) => {DISPLAY_OPTIONS.set(field.key, e)}}>
                      <Rb.ToggleButton value={true}>Yes</Rb.ToggleButton>
                      <Rb.ToggleButton value={false}>No</Rb.ToggleButton>
                    </Rb.ToggleButtonGroup>
                  </Rb.ButtonToolbar>),
                option: () => (
                  <Rb.FormControl componentClass="select" defaultValue={DISPLAY_OPTIONS.get(field.key)} onChange={(e) => {
                      DISPLAY_OPTIONS.set(field.key, e.target.value);
                    }}>
                    {_.zip(field.opts.keys, field.opts.values).map(([key, value]) =>
                      <option value={key} key={key}>{value}</option>)}
                  </Rb.FormControl>
                )
             }[field.type]()}
           </Rb.FormGroup>
           : <div key={i} />
        )}
      </form>
    </div>;
  }
}

@observer
class MetadataView extends React.Component {
  render() {
    (window.search_result.result); // ensure that we re-render when search result changes
    let keys = [
      ['Viewing',  [
        ['f', 'expand thumbnail'],
        ['p', 'play clip'],
        ['l', 'play clip in loop'],
        ['r', 'toggle playback speed']
      ]],
      ['Frame labeling', [
        ['click/drag', 'create bounding box'],
        ['d', 'delete bounding box'],
        ['g', 'cycle gender'],
        ['b', 'mark as background face'],
        ['s', 'select frames to save'],
        ['a', 'mark selected as labeled'],
         ['x', 'mark frame to ignore']
      ]],
      ['Track labeling', [
        ['m', 'merge current and last track'],
        ['t', 'start/end new track'],
        ['enter', 'skip to next track'],
        ['z', 'undo last action']
      ]]
    ];
    return <div className='metadata'>
      <h2>Metadata</h2>
      <div className='meta-block'>
        <div className='meta-key'>Type</div>
        <div className='meta-val'>{window.search_result.type}</div>
      </div>
      <div className='meta-block colors'>
        <div className='meta-key'>Labelers</div>
        <div className='meta-val'>
          {_.values(window.search_result.labelers).map((labeler, i) =>
            <div key={i}>
              {labeler.name}: &nbsp;
              <div style={{backgroundColor: window.search_result.labeler_colors[labeler.id],
                           width: '10px', height: '10px', display: 'inline-box'}} />
            </div>
          )}
          <div className='clearfix' />
        </div>
      </div>
      <div className='meta-block'>
        <div className='meta-key'>Count</div>
        <div className='meta-val'>{window.search_result.count}</div>
      </div>
      <h3>Help</h3>
      <div className='help'>
        On hover over a clip:
        {keys.map(([name, sec_keys], i) =>
          <div key={i} className='help-section'>
            <strong>{name}</strong>
          {sec_keys.map((entry, j) =>
            <div key={j}><code>{entry[0]}</code> - {entry[1]}</div>)}
          </div>
        )}
      </div>
    </div>;
  }
}

export default class SidebarView extends React.Component {
  render() {
    return <div>
      <div className='sidebar left'>
        <MetadataView />
      </div>
      <div className='sidebar right'>
        <OptionsView />
      </div>
    </div>;
  }
}
