'use strict';
const {dispatch: mediaDispatch} = require('./tests/browser_media.js');
const vm = require('node:vm');
const readline = require('node:readline');
async function dispatch(command) {
  if (command.op === 'syntax') {
    command.scripts.forEach(script => new vm.Script(script));
    return {events: [], active: [], pending: []};
  }
  return mediaDispatch(command);
}
process.on('unhandledRejection', error => {
  process.stderr.write(String(error.stack || error) + '\n');
  process.exit(2);
});

const lines = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
(async function () {
  for await (const line of lines) {
    if (Buffer.byteLength(line) > 8 * 1024 * 1024) break;
    try {
      process.stdout.write(JSON.stringify(await dispatch(JSON.parse(line))) + '\n');
    } catch (error) {
      process.stdout.write(JSON.stringify({error: String(error.stack || error)}) + '\n');
    }
  }
})();
