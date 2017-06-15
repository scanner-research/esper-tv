import React from 'react';
import {Video} from 'models/video.jsx';
import VideoSummary from 'views/video_summary.jsx';
import {observer} from 'mobx-react';
import mobx from 'mobx';
import _ from 'lodash';
import {Button, Collapse} from 'react-bootstrap';

@observer
class VideoView extends React.Component {
  constructor(...args) {
    super(...args);
    this.state = {
      showAllFaces: false,
      frame: 0,
      editMode: false,
      selectStart: null,
      selections: []
    };
  }

  render() {
    let video = this.props.store;

    if (!video.loadedMeta) {
      return <div>Loading video...</div>;
    }

    video.loadFaces();

    let table = [
      ['ID', video.id],
      ['Path', video.path],
      ['# frames', video.num_frames],
      ['FPS', video.fps],
      ['Resolution', `${video.width}x${video.height}`]];

    let makeFace = (face, j) => {
      // TODO: highlight selected face in different color
      let onClick = () => {
        if (this.state.editMode) {
          if (this.state.selectStart == null) {
            this.setState({selectStart: face});
          } else {
            this.state.selections.push([this.state.selectStart, face]);
            console.log(this.state.selections);
            this.setState({selectStart: null});
          }
        } else {
          this.setState({'frame': face.frame});
        }
      };

      let colors = [
        'red',
        'green',
        'blue',
        'yellow']

      let selected = false;
      let color = {};
      for (var i = 0; i < this.state.selections.length; ++i) {
        let [start, end] = this.state.selections[i];
        if (face.frame >= start.frame && face.frame <= end.frame &&
            face.identity == start.identity) {
          selected = true;
          color = {'borderColor': colors[i % colors.length]};
          break;
        }
      }
      return <img key={j} src={`/static/thumbnails/${face.video}_${face.id}.jpg`} onClick={onClick}
                  className={selected ? 'selected' : '' + ' gender-' + face.gender} style={color} />;
    };

    return (
      <div className="video">
        <div className="row">
          <div className="video-meta col-md-4">
            <VideoSummary store={video} frame={this.state.frame} show_meta={false} />
            <h2>Metadata</h2>
            <table className="table">
              <tbody>
                {table.map((pair, i) =>
                  <tr key={i}><td>{pair[0]}</td><td>{pair[1]}</td></tr>
                 )}
              </tbody>
            </table>
            <Button onClick={() => this.setState({editMode: !this.state.editMode})}>
              {this.state.editMode ? 'View mode' : 'Edit mode'}
            </Button>
          </div>
          <div className="video-faces col-md-8">
            {video.loadedFaces
             ? (<div>
               <div className="cluster">
                 <h3>All faces
                   &nbsp;
                   <Button onClick={() => this.setState({showAllFaces: !this.state.showAllFaces})}>
                     +
                   </Button>
                 </h3>
                 <Collapse in={this.state.showAllFaces}>
                   <div>
                     {_.map(video.faces, (faces, i) =>
                       <div className="frame" key={i}>
                         {faces.map(makeFace)}
                       </div>)}
                   </div>
                 </Collapse>
               </div>
               <div className="clusters">
                 {_.map(video.ids, (faces, i) =>
                   <div className={'cluster ' + (this.state.editMode ? 'editing' : '')} key={i}>
                     <h3>Cluster {i}</h3>
                     {faces.map((entry, j) => {
                        let [frame, face_index] = entry;
                        let frame_faces = video.faces[frame];
                        let face = frame_faces[face_index];
                        return makeFace(face, j);
                      })}
                   </div>
                  )}
               </div>
             </div>)
             : (<div>Loading faces...</div>)}
          </div>
        </div>
      </div>
    );
  }
};

export default (props) => <VideoView store={new Video(props.id)} />;
