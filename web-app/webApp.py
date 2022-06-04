#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from datetime import datetime
from flask import Flask, render_template

from cacheLib import *

app = Flask(__name__)


###############################  Flask Routes #################################

@app.route("/")
def index():
    return render_template('index.html', rows=max_rows, sql=sql)

@app.route("/query_mysql")
def query_mysql_endpoint():
    start_time = datetime.now()
    data = query_mysql(sql,configs['db_host'], configs['db_username'], configs['db_password'], configs['db_name'])
    delta = (datetime.now() - start_time).total_seconds()
    return render_template('query_mysql.html', delta=delta, data=data, sql=sql, fields=db_tbl_fields)

@app.route("/query_cache")
def query_cache_endpoint():
    data = None 
    start_time = datetime.now()
    result = query_mysql_and_cache(sql,configs['db_host'], configs['db_username'], configs['db_password'], configs['db_name'])
    delta = (datetime.now() - start_time).total_seconds()    

    if isinstance(result['data'], list):
        data = result['data']
    else:
        data = json.loads(result['data'])

    return render_template('query_cache.html', delta=delta, data=data, records_in_cache=result['records_in_cache'], 
                                TTL=Cache.ttl(sql), sql=sql, fields=db_tbl_fields)

@app.route("/delete_cache")
def delete_cache_endpoint():
    flush_cache()
    return render_template('delete_cache.html')    

if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=app_port)
    