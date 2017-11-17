import React from 'react';
import axios from 'axios';
import ReactDOM from 'react-dom';
import brace from 'brace';
import * as Rb from 'react-bootstrap';
import AceEditor from 'react-ace';
import {observer} from 'mobx-react';

import 'brace/mode/python'
import 'brace/theme/github'

@observer
class SchemaView extends React.Component {
  state = {
    loadingExamples: false,
    showExamples: false
  }

  examples = {}
  exampleField = ""

  _onClick = (cls_name, field) => {
    let full_name = cls_name + '.' + field;
    if (full_name == this.exampleField) {
      this.exampleField = '';
      this.setState({showExamples: false});
    } else {
      this.exampleField = full_name;
      if (this.examples.hasOwnProperty(full_name)) {
        this.setState({showExamples: true});
      } else {
        this.setState({showExamples: false, loadingExamples: true});
        axios
          .post('/api/schema', {dataset: window.DATASET, cls_name: cls_name, field: field})
          .then(((response) => {
            if (response.data.hasOwnProperty('error')) {
              this.examples[full_name] = false;
            } else {
              this.examples[full_name] = response.data['result'];
            }
            this.setState({showExamples: true});
          }).bind(this))
          .catch((error) => console.error(error))
          .then((() => {
            this.setState({loadingExamples: false});
          }));
      }
    }
  }

  render() {
    return (
      <div className='schema'>
        <div className='schema-classes'>
          {_.find(SCHEMAS.schemas, (l) => l[0] == window.DATASET)[1].map((cls, i) =>
            <Rb.Panel key={i} className='schema-class'>
              <div className='schema-class-name'>{cls[0]}</div>
              <div className='schema-class-fields'>
                {cls[1].map((field, j) =>
                  <div className='schema-field' key={j} onClick={() => this._onClick(cls[0], field)}>{field}</div>
                )}
              </div>
            </Rb.Panel>
          )}
        </div>
        {this.state.loadingExamples
         ? <img className='spinner' />
         : <div />}
        {this.state.showExamples
         ? <Rb.Panel className='schema-example'>
           <div className='schema-example-name'>{this.exampleField}</div>
           <div>
             {this.examples[this.exampleField]
              ? this.examples[this.exampleField].map((example, i) =>
                <div key={i}>{example}</div>
              )
              : <div>Field cannot be displayed (not serializable, likely binary data).</div>}
           </div>
         </Rb.Panel>
         : <div />}
      </div>
    );
  }
}

export default class SearchInputView extends React.Component {
  state = {
    searching: false,
    showSchema: false,
    showExampleQueries: false,
  }

  exampleQueries = [
    ["All videos",
     "result = qs_to_result(Frame.objects.filter(number=0))"],
    ["Fox News videos",
     "result = qs_to_result(Frame.objects.filter(number=0, video__channel='FOXNEWS'))"],
    ["Faces",
     "result = qs_to_result(FaceTrack.objects.filter(id__in=Face.objects.annotate(height=F('bbox_y2')-F('bbox_y1')).filter(frame__video__id=791, labeler__name='mtcnn', height__gte=0.3).distinct('track').values('track')), segment=True)"],
    ["Faces on Poppy Harlow",
     "result = qs_to_result(Face.objects.filter(frame__video__show='CNN Newsroom With Poppy Harlow'), group=True, stride=24)"],
    ["Female faces on Poppy Harlow",
     "result = qs_to_result(Face.objects.filter(frame__video__show='CNN Newsroom With Poppy Harlow', gender__name='female'), group=True, stride=24)"],
    ["'Talking heads' on Poppy Harlow",
     "result = qs_to_result(Face.objects.annotate(height=F('bbox_y2')-F('bbox_y1')).filter(height__gte=0.3, frame__video__show='CNN Newsroom With Poppy Harlow', gender__name='female'), group=True, stride=24)"],
    ["Two female faces on Poppy Harlow",
`r = []
for video in Video.objects.filter(show='CNN Newsroom With Poppy Harlow'):
    for frame in Frame.objects.filter(video=video).annotate(n=F('number')%math.ceil(video.fps)).filter(n=0)[:1000:10]:
        faces = list(Face.objects.annotate(height=F('bbox_y2')-F('bbox_y1')).filter(labeler__name='mtcnn', frame=frame, gender__name='female', height__gte=0.2))
        if len(faces) == 2:
            r.append({
                'video': frame.video.id,
                'start_frame': frame.id,
                'objects': [bbox_to_dict(f) for f in faces]
            })
result = {'result': r, 'count': '?', 'type': 'Frame'}`],
    ["Poses with feet", `
def pose_filter(fn, used, kp):
    for k in used:
        if kp[k][2] == 0: return False
    return fn(kp)

def has_feet(kp):
    return True

def hands_above_head(kp):
    return kp[Pose.LWrist][1] < kp[Pose.Nose][1] and kp[Pose.RWrist][1] < kp[Pose.Nose][1]

poses = Pose.objects.filter(bbox_score__gte=0).select_related('frame', 'frame__video').order_by('?')
filtered = []
for pose in poses[:1000]:
    if pose_filter(hands_above_head, [Pose.LWrist, Pose.Nose, Pose.RWrist], pose.pose_keypoints()):
    #if pose_filter(has_feet, [Pose.LAnkle, Pose.RAnkle], pose.pose_keypoints()):
        filtered.append(pose)

result = {
    'result': [
        {'video': p.frame.video.id,
        'start_frame': p.frame.id,
        'objects': [pose_to_dict(pp) for pp in Pose.objects.filter(frame=p.frame)][:100]}
        for p in filtered
    ],
    'count': len(filtered),
    'type': 'Pose'
}`],
    ["Faces like Poppy Harlow",
     `id = 4457280
FaceFeatures.dropTempFeatureModel()
FaceFeatures.getTempFeatureModel([id])
result = qs_to_result(Face.objects.all().order_by('facefeaturestemp__distto_{}'.format(id)))`],
    ["Faces unlike Poppy Harlow",
     `id = 4457280
FaceFeatures.dropTempFeatureModel()
FaceFeatures.getTempFeatureModel([id])
result = qs_to_result(Face.objects.filter(**{'facefeaturestemp__distto_{}__gte'.format(id): 1.7}).order_by('facefeaturestemp__distto_{}'.format(id)))`],
    ["Differing bounding boxes", `labeler_names = [l['labeler__name'] for l in Face.objects.values('labeler__name').distinct()]

videos = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
for frame in Frame.objects.filter(Q(video__show='Situation Room With Wolf Blitzer') | Q(video__show='Special Report With Bret Baier')).filter(face__labeler__name='handlabeled').select_related('video')[:50000:5]:
    faces = list(Face.objects.filter(frame=frame).select_related('labeler'))
    has_mtcnn = any([f.labeler.name == 'mtcnn' for f in faces])
    has_handlabeled = any([f.labeler.name == 'handlabeled' for f in faces])
    if not has_mtcnn or not has_handlabeled:
        continue
    for face in faces:
        videos[frame.video.id][frame.id][face.labeler.name].append(face)

AREA_THRESHOLD = 0.02
DIST_THRESHOLD = 0.10

mistakes = defaultdict(lambda: defaultdict(tuple))
for video, frames in videos.iteritems():
    for frame, labelers in frames.iteritems():
        for labeler, faces in labelers.iteritems():
            for face in faces:
                if bbox_area(face) < AREA_THRESHOLD:
                    continue

                mistake = True
                for other_labeler in labeler_names:
                    if labeler == other_labeler: continue
                    other_faces = labelers[other_labeler] if other_labeler in labelers else []
                    for other_face in other_faces:
                        if bbox_dist(face, other_face) < DIST_THRESHOLD:
                            mistake = False
                            break

                    if mistake and len(other_faces) > 0:
                        mistakes[video][frame] = (faces, other_faces)
                        break
                else:
                    continue
                break

result = []
for video, frames in list(mistakes.iteritems())[:100]:
    for frame, (faces, other_faces) in frames.iteritems():
        result.append({
            'video': video,
            'start_frame': frame,
            'objects': [bbox_to_dict(f) for f in faces + other_faces]
        })

result = {'result': result, 'count': len(result), 'type': 'Frame'}
`]
  ]

  query = `result = qs_to_result(Face.objects.all())`

  _onSearch = (e) => {
    e.preventDefault();
    this.setState({searching: true});
    axios
      .post('/api/search2', {dataset: window.DATASET, code: this._editor.editor.getValue()})
      .then((response) => {
        if (response.data.success) {
          this.props.onSearch(response.data.success);
        } else {
          console.error(response.data.error);
        }
      })
      .catch((error) => {
        console.error(error);
      })
      .then(() => {
        this.setState({searching: false});
      });
  }

  _onChangeDataset = (e) => {
    window.DATASET.set(e.target.value);
  }

  /* Hacks to avoid code getting wiped out when setState causes the form to re-render. */
  _onCodeChange = (newCode) => {
    this.query = newCode;
  }
  componentDidUpdate() {
    this._editor.editor.setValue(this.query, 1);
  }

  render() {
    return (
      <Rb.Form className='search-input' onSubmit={this._onSearch} ref={(n) => {this._form = n;}} inline>
        <AceEditor
          mode="python"
          theme="github"
          width='auto'
          minLines={1}
          maxLines={20}
          highlightActiveLine={false}
          showGutter={false}
          showPrintMargin={false}
          onChange={this._onCodeChange}
          defaultValue={this.query}
          editorProps={{$blockScrolling: Infinity}}
          ref={(n) => {this._editor = n;}} />
        <Rb.Button type="submit" disabled={this.state.searching}>Search</Rb.Button>
        <Rb.Button onClick={() => {this.setState({showSchema: !this.state.showSchema})}}>
          {this.state.showSchema ? 'Hide' : 'Show'} Schema
        </Rb.Button>
        <Rb.Button onClick={() => {this.setState({showExampleQueries: !this.state.showExampleQueries})}}>
          {this.state.showExampleQueries ? 'Hide' : 'Show'} Example Queries
        </Rb.Button>
        <Rb.FormGroup>
          <Rb.ControlLabel>Dataset:</Rb.ControlLabel>
          <Rb.FormControl componentClass="select" onChange={this._onChangeDataset} defaultValue={window.DATASET}>
            {SCHEMAS.schemas.map((l, i) =>
              <option key={i} value={l[0]}>{l[0]}</option>
            )}
          </Rb.FormControl>
        </Rb.FormGroup>
        {this.state.searching
         ? <img className='spinner' />
         : <div />}
        {this.state.showExampleQueries
         ? <Rb.Panel className='example-queries'>
           <strong>Example queries</strong><br />
           {this.exampleQueries.map((q, i) => {
              return (<span key={i}><a href="#" onClick={() => {this.query = q[1]; this.forceUpdate()}}>{q[0]}</a>
              <br /></span>);
           })}
           </Rb.Panel>
         : <div />}
        {this.state.showSchema ? <SchemaView /> : <div />}
      </Rb.Form>
    );
  }
}
