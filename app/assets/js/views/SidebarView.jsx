import React from 'react';
import {observer} from 'mobx-react';
import * as Rb from 'react-bootstrap';

@observer
class OptionsView extends React.Component {
  fields = [
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
      opts: {
        min: 1,
        max: 300,
        step: 1
      },
    },
    {
      name: 'Crop bboxes',
      key: 'crop_bboxes',
      type: 'radio'
    },
    {
      name: 'Show gender as border',
      key: 'show_gender_as_border',
      type: 'radio'
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
    },
    {
      name: 'Show pose',
      key: 'show_pose',
      type: 'radio',
    },
    {
      name: 'Show face',
      key: 'show_face',
      type: 'radio',
    },
    {
      name: 'Show left/right (blue/red)',
      key: 'show_lr',
      type: 'radio'
    },
  ]

  render() {
    return <div className='options'>
      <h2>Options</h2>
      <form>
        {this.fields.map((field, i) =>
           <Rb.FormGroup key={i}>
             <Rb.ControlLabel>{field.name}</Rb.ControlLabel>
             {{
                range: () => (
                  <span>
                    <input type="range" min={field.opts.min} max={field.opts.max}
                           step={field.opts.step} value={DISPLAY_OPTIONS.get(field.key)}
                           onChange={(e) => {DISPLAY_OPTIONS.set(field.key, e.target.value)}} />
                    <Rb.FormControl type="number" min={field.opts.min} max={field.opts.max}
                                    value={DISPLAY_OPTIONS.get(field.key)}
                                    onChange={(e) => {DISPLAY_OPTIONS.set(field.key, e.target.value)}} />
                  </span>),
                radio: () => (
                  <Rb.ButtonToolbar>
                    <Rb.ToggleButtonGroup type="radio" name={field.key} defaultValue={DISPLAY_OPTIONS.get(field.key)}
                                          onChange={(e) => {DISPLAY_OPTIONS.set(field.key, e)}}>
                      <Rb.ToggleButton value={true}>Yes</Rb.ToggleButton>
                      <Rb.ToggleButton value={false}>No</Rb.ToggleButton>
                    </Rb.ToggleButtonGroup>
                  </Rb.ButtonToolbar>)
             }[field.type]()}
           </Rb.FormGroup>
        )}
      </form>
    </div>;
  }
}

@observer
class MetadataView extends React.Component {
  render() {
    (window.search_result.result); // ensure that we re-render when search result changes
    let view_keys = [
      ['f', 'expand thumbnail'],
      ['p', 'play clip'],
      ['l', 'play clip in loop']
    ];
    let label_keys = [
      ['click/drag', 'create bounding box'],
      ['d', 'delete bounding box'],
      ['g', 'cycle gender'],
      ['b', 'mark as background face'],
      ['s', 'select frames to save'],
      ['a', 'mark selected as labeled'],
      ['x', 'mark frame to ignore']
      /* ['t', 'start track'],
       * ['q', 'add to track'],
       * ['u', 'delete track']*/
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
        <div>
          <strong>Viewing</strong>
          {view_keys.map((entry, i) =>
            <div key={i}><code>{entry[0]}</code> - {entry[1]}</div>)}
        </div>
        <div>
          <strong>Labeling</strong>
          {label_keys.map((entry, i) =>
            <div key={i}><code>{entry[0]}</code> - {entry[1]}</div>)}
        </div>
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
