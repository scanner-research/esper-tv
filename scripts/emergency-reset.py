from flask import Flask
import subprocess as sp

app = Flask(__name__)

page = """
<html>
<body>
<script>
function reset() {
  var r = new XMLHttpRequest();
  r.open('GET', '/reset', false);
  r.send();
  alert('Reset successful!');
}
</script>
<button onclick="reset()">EMERGENCY RESET</button>
</body>
</html>
"""


@app.route("/")
def index():
    return page


@app.route('/reset')
def reset():
    sp.check_call(
        'docker-compose stop -t 0 && docker-compose down && docker-compose up -d', shell=True)
    return ""
