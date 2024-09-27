from flask import Flask, jsonify, request
import json

app = Flask(__name__)

RMS = {'rms': [], 'var': []}


@app.route('/rms')
def get_incomes():
    return jsonify(RMS)


@app.route('/rms', methods=['POST'])
def add_income():
    global RMS
    rms_json = request.get_json()
    RMS = json.loads(rms_json)
    return '', 204


if __name__ == '__main__':
    app.run(debug=True)