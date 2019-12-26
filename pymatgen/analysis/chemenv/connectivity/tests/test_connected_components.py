#!/usr/bin/env python


__author__ = 'waroquiers'

import networkx as nx
from pymatgen.analysis.chemenv.connectivity.connected_components import ConnectedComponent
from pymatgen.analysis.chemenv.connectivity.connectivity_finder import ConnectivityFinder
from pymatgen.analysis.chemenv.connectivity.environment_nodes import EnvironmentNode
from pymatgen.analysis.chemenv.coordination_environments.coordination_geometry_finder import LocalGeometryFinder
from pymatgen.analysis.chemenv.coordination_environments.chemenv_strategies import SimplestChemenvStrategy
from pymatgen.analysis.chemenv.coordination_environments.structure_environments import LightStructureEnvironments
from pymatgen.core.sites import PeriodicSite
from pymatgen.core.lattice import Lattice
from pymatgen.core.structure import Structure
from pymatgen.util.testing import PymatgenTest

import bson
import json
import pytest
import numpy as np
import copy
import os


class ConnectedComponentTest(PymatgenTest):

    def test_init(self):
        # Generic connected component not using EnvironmentNodes
        # (as_dict won't work on such a ConnectedComponent instance)
        cc = ConnectedComponent(environments=['a', 'b', 'c', 'd', 'e', 'f'],
                                links=[('a', 'b', 0), ('a', 'c', 0), ('b', 'c', 0),
                                       ('a', 'a', 0), ('a', 'b', 1),
                                       ('c', 'd'), ('c', 'd'), ('c', 'd'), ('d', 'e'), ('e', 'f')],
                                environments_data={'a': {'var1': 2, 'var2': 3},
                                                   'b': {'var1': 3}},
                                links_data={('c', 'b'): {'bcinfo': 2},
                                            ('a', 'b', 1): {'ab1info': 4},
                                            ('d', 'c'): {'dcinfo': 8}})
        assert isinstance(cc.graph, nx.MultiGraph)
        nodes = list(cc.graph.nodes())
        assert set(nodes) == {'a', 'b', 'c', 'd', 'e', 'f'}
        edges = cc.graph.edges()
        assert len(edges) == 10
        assert cc.graph['a']['b'] == {0: {}, 1: {'ab1info': 4}}
        assert cc.graph['b']['a'] == {0: {}, 1: {'ab1info': 4}}
        assert cc.graph['c']['b'] == {0: {'bcinfo': 2}}
        assert cc.graph['b']['c'] == {0: {'bcinfo': 2}}
        assert len(cc.graph['c']['d']) == 3
        assert cc.graph['c']['d'][0] == {'dcinfo': 8}
        assert cc.graph['c']['d'][1] == {'dcinfo': 8}
        assert cc.graph['c']['d'][2] == {'dcinfo': 8}

        assert cc.graph.nodes(data=True)['a'] == {'var1': 2, 'var2': 3}
        assert cc.graph.nodes(data=True)['b'] == {'var1': 3}
        assert cc.graph.nodes(data=True)['c'] == {}

        # Make a deep copy of the graph to actually check that the objects are different instances
        mygraph = copy.deepcopy(cc.graph)
        assert isinstance(mygraph, nx.MultiGraph)  # Check that it is indeed the same type of graph

        cc2 = ConnectedComponent(graph=mygraph)
        assert set(list(mygraph.nodes())) == set(list(cc2.graph.nodes()))
        assert set(list(mygraph.edges())) == set(list(cc2.graph.edges()))
        assert len(cc2.graph) == 6

    def test_serialization(self):
        lat = Lattice.hexagonal(a=2.0, c=2.5)
        en1 = EnvironmentNode(central_site=PeriodicSite('Si',
                                                        coords=np.array([0.0, 0.0, 0.0]),
                                                        lattice=lat),
                              i_central_site=3, ce_symbol='T:4')
        en2 = EnvironmentNode(central_site=PeriodicSite('Ag',
                                                        coords=np.array([0.0, 0.0, 0.5]),
                                                        lattice=lat),
                              i_central_site=5, ce_symbol='T:4')
        en3 = EnvironmentNode(central_site=PeriodicSite('Ag',
                                                        coords=np.array([0.0, 0.5, 0.5]),
                                                        lattice=lat),
                              i_central_site=8, ce_symbol='O:6')

        graph = nx.MultiGraph()
        graph.add_nodes_from([en1, en2, en3])

        graph.add_edge(en1, en2, start=en1.isite, end=en2.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en1, en3, start=en1.isite, end=en2.isite,
                       delta=(0, 0, 0), ligands=[(10, (0, 0, 1), (0, 0, 1)), (11, (0, 0, 1), (0, 0, 1))])

        cc = ConnectedComponent(graph=graph)
        ref_sorted_edges = [[en1, en2], [en1, en3]]
        sorted_edges = sorted([sorted(e) for e in cc.graph.edges()])
        assert sorted_edges == ref_sorted_edges

        ccfromdict = ConnectedComponent.from_dict(cc.as_dict())
        ccfromjson = ConnectedComponent.from_dict(json.loads(json.dumps(cc.as_dict())))
        bson_data = bson.BSON.encode(cc.as_dict())
        ccfrombson = ConnectedComponent.from_dict(bson_data.decode())
        for loaded_cc in [ccfromdict, ccfromjson, ccfrombson]:
            assert loaded_cc.graph.number_of_nodes() == 3
            assert loaded_cc.graph.number_of_edges() == 2
            assert set(list(cc.graph.nodes())) == set(list(loaded_cc.graph.nodes()))
            assert sorted_edges == sorted([sorted(e) for e in loaded_cc.graph.edges()])

            for ii, e in enumerate(sorted_edges):
                assert cc.graph[e[0]][e[1]] == loaded_cc.graph[e[0]][e[1]]

            for node in loaded_cc.graph.nodes():
                assert isinstance(node.central_site, PeriodicSite)

    def test_serialization_private_methods(self):
        # Testing _edgekey_to_edgedictkey
        key = ConnectedComponent._edgekey_to_edgedictkey(3)
        assert key == '3'
        with pytest.raises(RuntimeError, match=r'Cannot pass an edge key which is a str '
                                               r'representation of an int\x2E'):
            key = ConnectedComponent._edgekey_to_edgedictkey('5')
        key = ConnectedComponent._edgekey_to_edgedictkey('mykey')
        assert key == 'mykey'
        with pytest.raises(ValueError, match=r'Edge key should be either a str or an int\x2E'):
            key = ConnectedComponent._edgekey_to_edgedictkey(0.2)

    def test_periodicity(self):
        en1 = EnvironmentNode(central_site='Si',
                              i_central_site=3, ce_symbol='T:4')
        en2 = EnvironmentNode(central_site='Ag',
                              i_central_site=5, ce_symbol='T:4')
        en3 = EnvironmentNode(central_site='Ag',
                              i_central_site=8, ce_symbol='O:6')
        en4 = EnvironmentNode(central_site='Fe',
                              i_central_site=23, ce_symbol='C:8')

        graph = nx.MultiGraph()
        graph.add_nodes_from([en1, en2, en3])
        graph.add_edge(en1, en2, start=en1.isite, end=en2.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en1, en3, start=en1.isite, end=en2.isite,
                       delta=(0, 0, 0), ligands=[(10, (0, 0, 1), (0, 0, 1)), (11, (0, 0, 1), (0, 0, 1))])
        cc = ConnectedComponent(graph=graph)
        assert cc.is_0d
        assert not cc.is_1d
        assert not cc.is_2d
        assert not cc.is_3d
        assert not cc.is_periodic
        assert cc.periodicity == '0D'

        graph = nx.MultiGraph()
        graph.add_nodes_from([en1, en2, en3])
        graph.add_edge(en1, en2, start=en1.isite, end=en2.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en1, en3, start=en1.isite, end=en3.isite,
                       delta=(0, 0, 0), ligands=[(10, (0, 0, 1), (0, 0, 1)), (11, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en2, en3, start=en2.isite, end=en3.isite,
                       delta=(0, 0, 1), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        cc = ConnectedComponent(graph=graph)
        assert not cc.is_0d
        assert cc.is_1d
        assert not cc.is_2d
        assert not cc.is_3d
        assert cc.is_periodic
        assert cc.periodicity == '1D'

        graph = nx.MultiGraph()
        graph.add_nodes_from([en1, en2, en3])
        graph.add_edge(en1, en2, start=en1.isite, end=en2.isite,
                       delta=(0, 0, 1), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en1, en3, start=en1.isite, end=en3.isite,
                       delta=(0, 0, 0), ligands=[(10, (0, 0, 1), (0, 0, 1)), (11, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en2, en3, start=en2.isite, end=en3.isite,
                       delta=(0, 0, -1), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        cc = ConnectedComponent(graph=graph)
        assert cc.periodicity == '0D'

        # Test errors when computing periodicity
        graph = nx.MultiGraph()
        graph.add_nodes_from([en1, en2, en3])
        graph.add_edge(en1, en1, start=en1.isite, end=en1.isite,
                       delta=(0, 0, 1), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en1, en1, start=en1.isite, end=en1.isite,
                       delta=(0, 0, 1), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        cc = ConnectedComponent(graph=graph)
        with pytest.raises(ValueError, match=r'There should not be self loops with the same '
                                             r'\x28or opposite\x29 delta image\x2E'):
            cc.compute_periodicity_all_simple_paths_algorithm()

        graph = nx.MultiGraph()
        graph.add_nodes_from([en1, en2, en3])
        graph.add_edge(en1, en1, start=en1.isite, end=en1.isite,
                       delta=(3, 2, -1), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en1, en1, start=en1.isite, end=en1.isite,
                       delta=(-3, -2, 1), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        cc = ConnectedComponent(graph=graph)
        with pytest.raises(ValueError, match=r'There should not be self loops with the same '
                                             r'\x28or opposite\x29 delta image\x2E'):
            cc.compute_periodicity_all_simple_paths_algorithm()

        graph = nx.MultiGraph()
        graph.add_nodes_from([en1, en2, en3])
        graph.add_edge(en1, en1, start=en1.isite, end=en1.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        cc = ConnectedComponent(graph=graph)
        with pytest.raises(ValueError, match=r'There should not be self loops with delta image = '
                                             r'\x280, 0, 0\x29\x2E'):
            cc.compute_periodicity_all_simple_paths_algorithm()

        # Test a 2d periodicity
        graph = nx.MultiGraph()
        graph.add_nodes_from([en1, en2, en3, en4])
        graph.add_edge(en1, en2, start=en1.isite, end=en2.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en1, en3, start=en1.isite, end=en3.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en4, en2, start=en4.isite, end=en2.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en3, en4, start=en4.isite, end=en3.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en3, en4, start=en4.isite, end=en3.isite,
                       delta=(0, -1, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en3, en2, start=en2.isite, end=en3.isite,
                       delta=(-1, -1, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        cc = ConnectedComponent(graph=graph)
        assert not cc.is_0d
        assert not cc.is_1d
        assert cc.is_2d
        assert not cc.is_3d
        assert cc.is_periodic
        assert cc.periodicity == '2D'
        assert np.allclose(cc.periodicity_vectors, [np.array([0, 1, 0]), np.array([1, 1, 0])])
        assert type(cc.periodicity_vectors) is list
        assert cc.periodicity_vectors[0].dtype is np.dtype(int)

        # Test a 3d periodicity
        graph = nx.MultiGraph()
        graph.add_nodes_from([en1, en2, en3, en4])
        graph.add_edge(en1, en2, start=en1.isite, end=en2.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en1, en3, start=en1.isite, end=en3.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en4, en2, start=en4.isite, end=en2.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en3, en4, start=en4.isite, end=en3.isite,
                       delta=(0, 0, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en3, en4, start=en4.isite, end=en3.isite,
                       delta=(0, -1, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en3, en2, start=en2.isite, end=en3.isite,
                       delta=(-1, -1, 0), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        graph.add_edge(en3, en3, start=en3.isite, end=en3.isite,
                       delta=(-1, -1, -1), ligands=[(2, (0, 0, 1), (0, 0, 1)), (1, (0, 0, 1), (0, 0, 1))])
        cc = ConnectedComponent(graph=graph)
        assert not cc.is_0d
        assert not cc.is_1d
        assert not cc.is_2d
        assert cc.is_3d
        assert cc.is_periodic
        assert cc.periodicity == '3D'
        assert np.allclose(cc.periodicity_vectors, [np.array([0, 1, 0]), np.array([1, 1, 0]), np.array([1, 1, 1])])
        assert type(cc.periodicity_vectors) is list
        assert cc.periodicity_vectors[0].dtype is np.dtype(int)

    def test_periodicity_real_systems(self):
        # Initialize geometry and connectivity finders
        strat = SimplestChemenvStrategy()
        lgf = LocalGeometryFinder()
        cf = ConnectivityFinder()

        # Connectivity of LiFePO4
        struct = self.get_structure('LiFePO4')
        lgf.setup_structure(structure=struct)
        se = lgf.compute_structure_environments(only_atoms=['Li', 'Fe', 'P'], maximum_distance_factor=1.2)
        lse = LightStructureEnvironments.from_structure_environments(strategy=strat, structure_environments=se)
        # Make sure the initial structure and environments are correct
        for isite in range(0, 4):
            assert lse.structure[isite].specie.symbol == 'Li'
            assert lse.coordination_environments[isite][0]['ce_symbol'] == 'O:6'
        for isite in range(4, 8):
            assert lse.structure[isite].specie.symbol == 'Fe'
            assert lse.coordination_environments[isite][0]['ce_symbol'] == 'O:6'
        for isite in range(8, 12):
            assert lse.structure[isite].specie.symbol == 'P'
            assert lse.coordination_environments[isite][0]['ce_symbol'] == 'T:4'
        # Get the connectivity including all environments and check results
        sc = cf.get_structure_connectivity(lse)
        assert len(sc.environment_subgraphs) == 0  # Connected component not computed by default
        ccs = sc.get_connected_components()  # by default, will use all the environments (O:6 and T:4 here)
        assert list(sc.environment_subgraphs.keys()) == ['O:6-T:4']  # Now connected components for the defaults are there
        assert len(sc.environment_subgraphs) == 1
        assert len(ccs) == 1
        cc = ccs[0]
        assert cc.periodicity == '3D'
        # Get the connectivity for T:4 and O:6 separately and check results
        # Only tetrahedral
        sc.setup_environment_subgraph(environments_symbols=['T:4'])
        assert list(sc.environment_subgraphs.keys()) == ['O:6-T:4', 'T:4']
        ccs = sc.get_connected_components()
        assert len(ccs) == 4
        for cc in ccs:
            assert cc.periodicity == '0D'
        # Only octahedral
        sc.setup_environment_subgraph(environments_symbols=['O:6'])
        assert list(sc.environment_subgraphs.keys()) == ['O:6-T:4', 'T:4', 'O:6']
        ccs = sc.get_connected_components()
        assert len(ccs) == 1
        cc = ccs[0]
        assert cc.periodicity == '3D'
        # Only Manganese octahedral
        sc.setup_environment_subgraph(environments_symbols=['O:6'], only_atoms=['Fe'])
        assert list(sc.environment_subgraphs.keys()) == ['O:6-T:4', 'T:4', 'O:6', 'O:6#Fe']
        ccs = sc.get_connected_components()
        assert len(ccs) == 2
        for cc in ccs:
            assert cc.periodicity == '2D'

        # Connectivity of Li4Fe3Mn1(PO4)4
        struct = Structure.from_file(os.path.join(self.TEST_FILES_DIR, 'Li4Fe3Mn1(PO4)4.cif'))
        lgf.setup_structure(structure=struct)
        se = lgf.compute_structure_environments(only_atoms=['Li', 'Fe', 'Mn', 'P'], maximum_distance_factor=1.2)
        lse = LightStructureEnvironments.from_structure_environments(strategy=strat, structure_environments=se)
        # Make sure the initial structure and environments are correct
        for isite in range(0, 4):
            assert lse.structure[isite].specie.symbol == 'Li'
            assert lse.coordination_environments[isite][0]['ce_symbol'] == 'O:6'
        for isite in range(4, 5):
            assert lse.structure[isite].specie.symbol == 'Mn'
            assert lse.coordination_environments[isite][0]['ce_symbol'] == 'O:6'
        for isite in range(5, 8):
            assert lse.structure[isite].specie.symbol == 'Fe'
            assert lse.coordination_environments[isite][0]['ce_symbol'] == 'O:6'
        for isite in range(8, 12):
            assert lse.structure[isite].specie.symbol == 'P'
            assert lse.coordination_environments[isite][0]['ce_symbol'] == 'T:4'
        # Get the connectivity including all environments and check results
        sc = cf.get_structure_connectivity(lse)
        assert len(sc.environment_subgraphs) == 0  # Connected component not computed by default
        ccs = sc.get_connected_components()  # by default, will use all the environments (O:6 and T:4 here)
        assert list(sc.environment_subgraphs.keys()) == ['O:6-T:4']  # Now connected components for the defaults are there
        assert len(sc.environment_subgraphs) == 1
        assert len(ccs) == 1
        cc = ccs[0]
        assert cc.periodicity == '3D'
        # Get the connectivity for Li octahedral only
        ccs = sc.get_connected_components(environments_symbols=['O:6'], only_atoms=['Li'])
        assert list(sc.environment_subgraphs.keys()) == ['O:6-T:4', 'O:6#Li']
        assert len(ccs) == 2
        for cc in ccs:
            assert cc.periodicity == '1D'
        # Get the connectivity for Mn octahedral only
        ccs = sc.get_connected_components(environments_symbols=['O:6'], only_atoms=['Mn'])
        assert list(sc.environment_subgraphs.keys()) == ['O:6-T:4', 'O:6#Li', 'O:6#Mn']
        assert len(ccs) == 1
        assert ccs[0].periodicity == '0D'
        # Get the connectivity for Fe octahedral only
        ccs = sc.get_connected_components(environments_symbols=['O:6'], only_atoms=['Fe'])
        assert list(sc.environment_subgraphs.keys()) == ['O:6-T:4', 'O:6#Li', 'O:6#Mn', 'O:6#Fe']
        assert len(ccs) == 2
        ccs_periodicities = set(cc.periodicity for cc in ccs)
        assert ccs_periodicities == {'0D', '2D'}