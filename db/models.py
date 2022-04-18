import importlib

import networkx as nx

from django.db import models
from .manager import DiGraphManager, DiGraphDescriptor


class Edge():

    bases = (models.Model, )
    model_object_name_suffix = 'DiGraphEdge'

    def __init__(self, state_model, edge_attr_model):
        self.state_model = state_model
        self.edge_attr_model = edge_attr_model

    def _get_name(self):
        return '{}{}'.format(
            self.state_model._meta.object_name, self.model_object_name_suffix
        )

    def get_model(self):
        attrs = {
            '__module__': self.state_model.__module__,
        }
        fields = self._get_fields()
        name = self._get_name()
        attrs.update(fields)
        model = type(str(name), self.bases, attrs)
        return model

    def _get_fields(self):
        fields = {
            'next_state':
                models.ForeignKey(self.state_model, on_delete=models.CASCADE),
            'attr':
                models.ForeignKey(
                    self.edge_attr_model, on_delete=models.SET_NULL, null=True
                )
        }
        return fields


class DiGraphModel():

    edge_meta_cls = Edge
    bases = (models.Model, )
    model_object_name_suffix = 'DiGraph'
    descriptor_cls = DiGraphDescriptor

    def __init__(self, edge_attr_model, *args, **kwargs):
        self.edge_attr_model = edge_attr_model

    def _get_fields(self, sender, edge_model):
        fields = {
            'edges': models.ManyToManyField(edge_model),
            'source':
                models.OneToOneField(
                    sender, on_delete=models.SET_NULL, null=True
                )
        }
        return fields

    def _get_name(self):
        return '{}{}'.format(
            self.sender_model._meta.object_name, self.model_object_name_suffix
        )
      
    def contribute_to_class(self, cls, name):
        self.manager_name = name
        self.module = cls.__module__
        self.cls = cls
        models.signals.class_prepared.connect(self._finalize, weak=False)

    def create_edge_model(self, sender):
        edge_meta = self.edge_meta_cls(sender, self.edge_attr_model)
        edge_model = edge_meta.get_model()
        return edge_model

    def create_graph_model(self, sender):
        attrs = {
            '__module__': self.module,
        }
        edge = self.create_edge_model(sender)
        fields = self._get_fields(sender, edge)
        name = self._get_name()
        attrs.update(fields)
        model = type(str(name), self.bases, attrs)

        # Below is for if we want to access like
        # app_name.models.ModelDiGraph, app_name.models.ModelDiGraphEdge etc.
        # but in this we don't required to access explicity.

        module = importlib.import_module(self.module)
        setattr(module, model.__name__, model)
        descriptor = self.descriptor_cls(model, self.manager_name)
        setattr(sender, self.manager_name, descriptor)

    def _finalize(self, sender, **kwargs):
        if self.cls is not sender:
            return
        self.sender_model = sender
        self.create_graph_model(sender)

        # Invoke if source model save
        models.signals.post_save.connect(
            self.post_save, sender=sender, weak=False
        )

        # Invoke if source model delete
        models.signals.post_delete.connect(
            self.post_delete, sender=sender, weak=False
        )

    def post_save(self, instance, created, using=None, **kwargs):
        manager = getattr(instance, self.manager_name)
        if manager.filter(source=instance).exists():
            return
        digraph_model_instance = manager.model()

        # source key fixed here, #TODO make user choosen
        digraph_model_instance.source = instance
        digraph_model_instance.save()

    def post_delete(self, instance, using=None, **kwargs):
        pass
