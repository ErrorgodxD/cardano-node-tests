"""Tests for KES period."""
import json
import logging
import time
from pathlib import Path

import allure
import pytest
from _pytest.tmpdir import TempdirFactory

from cardano_node_tests.utils import clusterlib
from cardano_node_tests.utils import devops_cluster
from cardano_node_tests.utils import helpers
from cardano_node_tests.utils import parallel_run

LOGGER = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def temp_dir(tmp_path_factory: TempdirFactory):
    """Create a temporary dir and change to it."""
    tmp_path = Path(tmp_path_factory.mktemp(helpers.get_id_for_mktemp(__file__)))
    with helpers.change_cwd(tmp_path):
        yield tmp_path


@pytest.fixture(scope="module")
def short_kes_start_cluster(tmp_path_factory: TempdirFactory) -> Path:
    """Update "slotsPerKESPeriod" and "maxKESEvolutions"."""
    pytest_globaltemp = helpers.get_pytest_globaltemp(tmp_path_factory)

    # need to lock because this same fixture can run on several workers in parallel
    with helpers.FileLockIfXdist(f"{pytest_globaltemp}/startup_files_short_kes.lock"):
        destdir = pytest_globaltemp / "startup_files_short_kes"
        destdir.mkdir(exist_ok=True)

        # return existing script if it is already generated by other worker
        if (destdir / "start-cluster").exists():
            return destdir / "start-cluster"

        startup_files = devops_cluster.copy_startup_files(destdir=destdir)
        with open(startup_files.genesis_spec) as fp_in:
            genesis_spec = json.load(fp_in)

        genesis_spec["slotsPerKESPeriod"] = 300
        genesis_spec["maxKESEvolutions"] = 5

        with open(startup_files.genesis_spec, "wt") as fp_out:
            json.dump(genesis_spec, fp_out)

        return startup_files.start_script


@pytest.fixture
def cluster_kes(
    cluster_manager: parallel_run.ClusterManager, short_kes_start_cluster: Path
) -> clusterlib.ClusterLib:
    return cluster_manager.get(singleton=True, cleanup=True, start_cmd=str(short_kes_start_cluster))


# use the "temp_dir" fixture for all tests automatically
pytestmark = pytest.mark.usefixtures("temp_dir")


class TestKES:
    """Basic tests for KES period."""

    @allure.link(helpers.get_vcs_link())
    def test_expired_kes(
        self,
        cluster_kes: clusterlib.ClusterLib,
    ):
        """Test expired KES."""
        cluster = cluster_kes

        expire_timeout = int(
            cluster.slots_per_kes_period * cluster.slot_length * cluster.max_kes_evolutions + 1
        )

        LOGGER.info(f"Waiting for {expire_timeout} sec for KES expiration.")
        time.sleep(expire_timeout)

        init_slot = cluster.get_last_block_slot_no()
        init_kes_period = cluster.get_last_block_kes_period()

        kes_period_timeout = int(cluster.slots_per_kes_period * cluster.slot_length + 1)
        LOGGER.info(f"Waiting for {kes_period_timeout} sec for next KES period.")
        time.sleep(kes_period_timeout)

        assert cluster.get_last_block_slot_no() == init_slot, "Unexpected new slots"
        assert cluster.get_last_block_kes_period() == init_kes_period, "Unexpected new KES period"
