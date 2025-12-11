"""
eCUDO Orchestration

Parallel processing orchestration for high-throughput crawling.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2025 Onedata (onedata.org)"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"

from ecudo.orchestration.parallel import ProcessingStats, run_parallel_pipeline

__all__ = ["run_parallel_pipeline", "ProcessingStats"]
