# Running Tests and experimenting locally

## Running Tests Locally with one version of python on mac

### [OPTIONAL / deprecated for now] install postgres - 
* _This is deprecated because for now we are using sqlite for testing_
* _In time, we may add this back_
* we need `pg_config` to be installed in order to install python locally,
  (that's the only reason we need postgres installed; docker-compose serves postgres for testing)
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
TBD

## Running Elasticsearch and Kibana locally
* `docker compose up` should bring up kibana as long as it's uncommented
  * It will take a while to start up
* run `make test` to run tests, which should create the schema in elasticsearch
* run `./manage.py es_update all` to update all the indexes
  * At some point you'll see `"message":"Server running at http://0:5601"}` in kibana service logs
  * When kibana is ready, you should see `test_movies-1` schema at http://0.0.0.0:5601/ in kibana under `discover`
