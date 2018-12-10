import scannertools as st
from scannerpy import Database
import os
import socket
import subprocess as sp

def join_path(src_cls, dest_cls):
    from collections import defaultdict
    from django.apps import apps

    models = apps.get_models()

    def key(m):
        return m._meta.db_table

    def join_graph():
        edges = defaultdict(list)
        edge_fields = defaultdict(dict)
        for model in models:
            for field in model._meta.get_fields():
                if field.is_relation and hasattr(field, 'column') and not field.null:
                    edges[key(model)].append(key(field.related_model))
                    edge_fields[key(model)][key(field.related_model)] = field

        return edges, edge_fields

    def bfs(join_graph):
        frontier = set([key(src_cls)])
        visited = set()
        paths = {key(src_cls): []}

        while len(frontier) > 0:
            new_frontier = set()
            for node in frontier:
                adjacent_unvisited = set(join_graph[node]) - visited - frontier
                for other in adjacent_unvisited:
                    paths[other] = paths[node] + [node]
                new_frontier |= adjacent_unvisited

            visited |= frontier
            frontier = new_frontier

        return {k: v + [k] for k, v in paths.items()}

    keymap = {key(m): m for m in models}
    graph, fields = join_graph()
    paths = bfs(graph)
    path = paths[key(dest_cls)]
    return [
        fields[path[i]][path[i+1]]
        for i in range(len(path) - 1)
    ]


class ScannerWrapper:
    def __init__(self, db, cluster=None):
        self.db = db
        self.cluster = cluster

    @classmethod
    def create(cls, cluster=None, multiworker=False, **kwargs):
        if cluster is not None:
            db = cluster.database(**kwargs)

        else:
            workers = ['localhost:{}'.format(5002 + i)
                       for i in range(mp.cpu_count() // 8)] if multiworker else None
            # import scannerpy.libscanner as bindings
            # import scanner.metadata_pb2 as metadata_types
            # params = metadata_types.MachineParameters()
            # params.ParseFromString(bindings.default_machine_params())
            # params.num_load_workers = 2
            # params.num_save_workers = 2
            db = Database(
                #machine_params=params.SerializeToString(),
                workers=workers,
                **kwargs)

        return cls(db, cluster)

    def sql_config(self):
        return self.db.protobufs.SQLConfig(
            adapter='postgres',
            hostaddr=socket.gethostbyname('db') if self.db._start_cluster else '127.0.0.1',
            port=5432,
            dbname='esper',
            user=os.environ['DJANGO_DB_USER'],
            password=os.environ['DJANGO_DB_PASSWORD'])

    def sql_source(self, cls):
        from query.models import Frame, Video
        table = cls._meta.db_table
        def joins(dst):
            return ['INNER JOIN {dst} ON {src}.{srcfield} = {dst}.{dstfield}'.format(
                src=field.model._meta.db_table,
                srcfield=field.column,
                dst=field.related_model._meta.db_table,
                dstfield='id')
                for field in join_path(cls, dst)]
        return self.db.sources.SQL(
            config=self.sql_config(),
            query=self.db.protobufs.SQLQuery(
                fields=','.join([
                    '{}.{} as {}'.format(table, field.name, field.name)
                    for field in cls._meta.get_fields()
                    if not field.is_relation
                ]),
                id='{}.id'.format(Frame._meta.db_table),
                group='{}.number'.format(Frame._meta.db_table),
                table='{} {}'.format(table, ' '.join(joins(Video)))
            ))

    def sql_source_args(self, video, num_elements=None):
        from query.models import Video
        return {
            'filter': '{}.id = {}'.format(Video._meta.db_table, video.id),
            'num_elements': num_elements if num_elements is not None else 0
        }

    def sql_sink(self, cls, input, videos, suffix, insert=True, ignore_conflicts=True):
        from query.models import ScannerJob
        sink = self.db.sinks.SQL(
            config=self.sql_config(),
            input=input,
            table=cls._meta.db_table,
            job_table=ScannerJob._meta.db_table,
            insert=insert,
            ignore_conflicts=ignore_conflicts)
        args = [{'job_name': '{}_{}'.format(v.path, suffix)} for v in videos]
        return st.BoundOp(op=sink, args=args)

    # Remove videos that don't have a table or have already been processed by the pipeline
    def filter_videos(self, videos, pipeline):
        from query.models import ScannerJob
        suffix = pipeline.job_suffix
        assert suffix is not None

        processed = set([
            t['name'] for t in ScannerJob.objects.filter(name__contains=suffix).values('name')])

        return [
            v for v in videos if self.db.has_table(v.path) and not '{}_{}'.format(v.path, suffix) in processed
        ]


class ScannerSQLTable(st.DataSource):
    def __init__(self, cls, video, num_elements=None):
        self._cls = cls
        self._video = video
        self._num_elements = num_elements

    def scanner_source(self, db):
        return ScannerWrapper(db).sql_source(self._cls)

    def scanner_args(self, db):
        return ScannerWrapper(db).sql_source_args(self._video, num_elements=self._num_elements)


class ScannerSQLPipeline:
    json_kernel = None
    db_class = None
    _job_cache = None

    def build_sink(self, db_videos):
        self._json_kernel_instance = getattr(self._db.ops, self.json_kernel)(**self._output_ops)
        return ScannerWrapper(self._db).sql_sink(
            cls=self.db_class, input=self._json_kernel_instance, videos=db_videos, suffix=self.job_suffix, insert=True)

    def committed(self, output):
        from query.models import ScannerJob
        if self._job_cache is None:
            self._job_cache = set(
                [r['name']
                 for r in ScannerJob.objects.filter(name__contains=self.job_suffix).values('name')])
        return output['job_name'] in self._job_cache

    def parse_output(self):
        pass
