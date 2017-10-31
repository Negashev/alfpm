import copy
import os

import re
import requests
import hashlib
from prometheus_client import make_wsgi_app
from prometheus_client.parser import text_string_to_metric_families
from wsgiref.simple_server import make_server

from prometheus_client.core import GaugeMetricFamily, REGISTRY
from apscheduler.schedulers.background import BackgroundScheduler

url = os.getenv('METRIC_HOST', 'http://localhost')
path = os.getenv('METRIC_PATH', 'metrics')
port = int(os.getenv('METRIC_PORT', 8080))
source_label = os.getenv('SOURCE_LABEL')
url_request = f'{url}:{port}/{path}'
collected_dict = {}


def hashFor(data):
    # Prepare the project id hash
    hashId = hashlib.md5()

    hashId.update(repr(data).encode('utf-8'))

    return hashId.hexdigest()


def collect():
    global collected_dict
    metricsFamily = {}
    for i in text_string_to_metric_families(requests.get(url_request).text):
        if i.samples[0][0] in ['process_cpu_seconds_total',
                               'process_virtual_memory_bytes',
                               'process_resident_memory_bytes',
                               'process_start_time_seconds',
                               'process_max_fds',
                               'process_open_fds',
                               'process_fake_namespace']:
            continue
        for item in i.samples:
            find_source = '*'
            if source_label in item[1]:
                find_source = item[1][source_label]
                if os.environ.get('SOURCE_REGEXP') is not None:
                    searched = re.search(os.getenv('SOURCE_REGEXP', '(.*)'), item[1][source_label], re.IGNORECASE)
                    if searched:
                        find_source = searched.group(1)

            sourceKey = ['environment']
            sourceValue = [find_source]
            list_keys = list(item[1].keys()) + sourceKey
            hash_list_keys = hashFor(list_keys)
            if hash_list_keys not in metricsFamily.keys():
                metricsFamily[hash_list_keys] = GaugeMetricFamily(item[0], i.documentation,
                                                                  labels=list_keys)
            metricsFamily[hash_list_keys].add_metric(list(item[1].values()) + sourceValue, value=item[2])
    collected_dict = metricsFamily


class CustomCollector(object):
    def collect(self):
        global collected_dict
        self.collected_dict = copy.deepcopy(collected_dict)
        for key in self.collected_dict.keys():
            yield self.collected_dict[key]


REGISTRY.register(CustomCollector())

scheduler = BackgroundScheduler(timezone="UTC")
scheduler.add_job(collect, 'interval', seconds=int(os.getenv('COLLECT_INTERVAL', 10)), max_instances=1)
scheduler.start()
app = make_wsgi_app()
httpd = make_server('0.0.0.0', 9101, app)
httpd.serve_forever()
