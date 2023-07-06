# Running Tests

## Running Tests Locally with one version of python on mac

### install postgres - [deprecated / optional for now]
* _This is deprecated because for now we are using sqlite for testing_
* _In time, we may add this back_
* we need `pg_config` to be installed in order to use python locally
* `brew install postgresql`
  * you may need to do `brew tap homebrew/core` first

### install version(s) of python you want to test with 
* install pyenv
* use it to install python 3.9 and 3.10, or the versions you care about
* `pyenv local 3.9.17 3.10.11` or whatever versions you want

### install pip deps
* `make requirements` to install pip deps
  * note that this requires `pg_config` to be on PATH

### run tests
* in another terminal, bring up dockerized postgres: `docker compose up`
* `make test` to run tests

## Running Tests Locally with multiple versions of python on mac

