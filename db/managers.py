import networkx as nx

from packaging import version as versioncheck

from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from networkx import DiGraph


class DiGraphPlugin(DiGraph):

    def __init__(self, instance, connection, *args, **kwargs):
        self.connection = connection
        self.instance = instance
        super().__init__(*args, **kwargs)


class DiGraphQuerySet(models.QuerySet):

    def filter(self, *args, **kwargs):
        return super().filter(*args, **kwargs)


class DiGraphDescriptor:

    def __init__(self, model, manager_name):
        self.model = model
        self.manager_name = manager_name

    def __get__(self, instance, owner):
        return DiGraphManager.from_queryset(
            DiGraphQuerySet, self.manager_name
        )(self.model, instance)


class DiGraphManager(models.Manager):

    def __init__(self, model, instance=None, graph_plugin=DiGraphPlugin):
        super().__init__()
        self.model = model
        self.instance = instance
        self.graph_plugin = graph_plugin

    def get_super_queryset(self):
        return super().get_queryset()

    def get_queryset(self):
        qs = self.get_super_queryset()
        if self.instance is None:
            return qs

        if isinstance(self.instance._meta.pk, models.ForeignKey):
            key_name = self.instance._meta.pk.name + "_id"
        else:
            key_name = self.instance._meta.pk.name

        # foreignkey fixed of source related object
        # TODO: make user dynamic
        key_name = 'source'

        return self.get_super_queryset().filter(**{key_name: self.instance.pk})

    def _get_digraph_obj(self):
        if not self.instance:
            return
        return getattr(self.instance, self.model._meta.model_name)

    @property
    def edges(self):
        return self._get_digraph_obj().edges.all()
    def _check_edge_valid(self, edge):
        # check if edge have all information.
        try:
            edge.next_state
        except ObjectDoesNotExist:
            raise ValueError("Edge is incomplete next_state is required.")
        # verify edge object
        if not isinstance(edge, self.get_edge_prototype().__class__):
            raise ValueError(
                f"Got invalid edge type {type(edge)}. "
                f"Expected: {self.model.__class__}"
            )

        # check if edge already in db
        if edge.pk:
            raise ValueError(
                "Only new edge can be added. "
                f"This edge already exists. id: {edge.pk}"
            )

        # check if edge is already there.
        edges = self.edges()
        if edge in edges:
            raise ValueError(
                "Unable to create edge, "
                "Same edge already exists."
            )

    def add_edge(self, edge):
        self._check_edge_valid(edge)
        digraph_instance = self._get_digraph_obj()
        edge.save()
        digraph_instance.edges.add(edge)
        digraph_instance.save()
        return edge

    def remove_edge(self, edge):
        pass

    def generate_networkx_digraph(self):
        if not self.instance:
            raise ValueError("get_graph can be called only from instance")
        digraph_nx = self._prepare_graph_from_instance(
            g=nx.MultiDiGraph(), source_=None
        )
        return digraph_nx

    @property
    def get_edge_prototype(self):
        return self.model.edges.rel.model()

    def _prepare_graph_from_instance(self, g=nx.MultiDiGraph(), source_=None):
        if not source_:
            source_ = self.instance
        edges = source_.digraph.edges()
        for edge in edges:
            next_state = edge.next_state
            if g.has_edge(source_, next_state, key=edge.attr):
                continue
            g.add_edge(source_, next_state, key=edge.attr)
            return self._prepare_graph_from_instance(g, source_=next_state)
        return g
