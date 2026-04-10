"""Shared loop utilities for agent runners and app modes."""

from typing import Callable, Optional


class AgentLoop:
    """Small shared loop helper for stop logic."""

    def __init__(self, max_iterations: Optional[int]):
        self.max_iterations = max_iterations
        self.unbounded = max_iterations is None or max_iterations <= 0

    def is_final_iteration(self, iteration_idx: int) -> bool:
        if self.unbounded:
            return False
        return iteration_idx >= self.max_iterations - 1

    def run(self, step_fn: Callable[[int], bool]) -> None:
        """Run loop and stop when step_fn returns True."""
        if self.unbounded:
            iteration_idx = 0
            while True:
                should_stop = step_fn(iteration_idx)
                if should_stop:
                    break
                iteration_idx += 1
            return

        for iteration_idx in range(self.max_iterations):
            should_stop = step_fn(iteration_idx)
            if should_stop:
                break

