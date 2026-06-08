import unittest
from pathlib import Path
import sys

CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = next(parent for parent in CURRENT_FILE.parents if (parent / "src").is_dir())
SRC_ROOT = PROJECT_ROOT / "src"
for path in (PROJECT_ROOT, SRC_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from failure_and_attribution_analysis.agent_failure_evaluator import build_default_failure_evaluator
from iterative_testing.iterative_failure_simulation import ClosedLoopFailureSimulation


NO_ATTACK_SCENARIO = {
    "StateObservationAttack_level": 0,
    "ActionAttack_level": 0,
    "StateTransferAttack_level": 0,
    "RewardAttack_level": 0,
    "ExperiencePoolAttack_level": 0,
    "ModelTampAttack_level": 0,
}

CONSTELLATION_0_NO_ATTACK_SCENARIO = {**NO_ATTACK_SCENARIO, "ConstellationConfig": 0}
CONSTELLATION_2_NO_ATTACK_SCENARIO = {**NO_ATTACK_SCENARIO, "ConstellationConfig": 2}


class InitialBaselineEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = build_default_failure_evaluator()

    def test_healthy_no_attack_baseline(self):
        result = self.evaluator._evaluate_baseline_status(
            scenario=dict(NO_ATTACK_SCENARIO),
            terminal_metrics={"AverageEndingReward": 0.70, "PacketLossRate": 0.10},
            terminal_hard_failure=False,
            true_failure_v2=False,
        )

        self.assertEqual(result["baseline_status"], "healthy")
        self.assertTrue(result["baseline_valid"])
        self.assertFalse(result["baseline_warning"])
        self.assertEqual(result["baseline_reason_codes"], [])

    def test_operable_no_attack_baseline(self):
        result = self.evaluator._evaluate_baseline_status(
            scenario=dict(NO_ATTACK_SCENARIO),
            terminal_metrics={"AverageEndingReward": 0.50, "PacketLossRate": 0.20},
            terminal_hard_failure=False,
            true_failure_v2=False,
        )

        self.assertEqual(result["baseline_status"], "operable")
        self.assertTrue(result["baseline_valid"])
        self.assertFalse(result["baseline_warning"])
        self.assertIn("reward_below_healthy", result["baseline_reason_codes"])
        self.assertIn("packet_loss_above_healthy", result["baseline_reason_codes"])

    def test_invalid_no_attack_baseline(self):
        result = self.evaluator._evaluate_baseline_status(
            scenario=dict(NO_ATTACK_SCENARIO),
            terminal_metrics={"AverageEndingReward": 0.40, "PacketLossRate": 0.10},
            terminal_hard_failure=False,
            true_failure_v2=False,
        )

        self.assertEqual(result["baseline_status"], "invalid")
        self.assertFalse(result["baseline_valid"])
        self.assertIn("reward_below_operable", result["baseline_reason_codes"])

    def test_warning_on_true_failure_v2_for_valid_baseline(self):
        result = self.evaluator._evaluate_baseline_status(
            scenario=dict(NO_ATTACK_SCENARIO),
            terminal_metrics={"AverageEndingReward": 0.70, "PacketLossRate": 0.10},
            terminal_hard_failure=False,
            true_failure_v2=True,
        )

        self.assertEqual(result["baseline_status"], "healthy")
        self.assertTrue(result["baseline_warning"])
        self.assertIn("true_failure_v2_warning", result["baseline_reason_codes"])

    def test_attack_scenario_is_not_applicable(self):
        scenario = dict(NO_ATTACK_SCENARIO)
        scenario["RewardAttack_level"] = 1
        result = self.evaluator._evaluate_baseline_status(
            scenario=scenario,
            terminal_metrics={"AverageEndingReward": 0.20, "PacketLossRate": 0.80},
            terminal_hard_failure=True,
            true_failure_v2=True,
        )

        self.assertEqual(result["baseline_status"], "not_applicable")
        self.assertTrue(result["baseline_valid"])
        self.assertFalse(result["baseline_warning"])

    def test_non_constellation_two_hard_failure_logic_is_unchanged(self):
        metrics = {
            "AverageEndingReward": 0.49,
            "PacketLossRate": 0.10,
            "AverageE2eDelay": 2.0,
            "NetworkThroughput": 100.0,
        }

        result = self.evaluator._terminal_hard_failure(
            metrics,
            reward_threshold=0.5,
            scenario=dict(CONSTELLATION_0_NO_ATTACK_SCENARIO),
        )

        self.assertTrue(result)

    def test_constellation_two_fragile_baseline_is_not_direct_hard_fail(self):
        metrics = {
            "AverageEndingReward": 0.33,
            "PacketLossRate": 0.18,
            "AverageE2eDelay": 3.75,
            "NetworkThroughput": 5305.0,
        }

        result = self.evaluator._terminal_hard_failure(
            metrics,
            reward_threshold=0.5,
            scenario=dict(CONSTELLATION_2_NO_ATTACK_SCENARIO),
        )

        self.assertFalse(result)

    def test_constellation_two_non_hard_fail_baseline_uses_fragile_profile(self):
        result = self.evaluator._evaluate_baseline_status(
            scenario=dict(CONSTELLATION_2_NO_ATTACK_SCENARIO),
            terminal_metrics={"AverageEndingReward": 0.40, "PacketLossRate": 0.10},
            terminal_hard_failure=False,
            true_failure_v2=False,
        )

        self.assertEqual(result["baseline_status"], "fragile")
        self.assertTrue(result["baseline_valid"])
        self.assertEqual(result["baseline_profile"], "constellation_2")
        self.assertIn("constellation2_fragile_baseline", result["baseline_reason_codes"])
        self.assertIn("constellation2_reward_drop_vs_anchor", result["baseline_reason_codes"])
        self.assertNotIn("constellation2_terminal_hard_failure", result["baseline_reason_codes"])

    def test_constellation_two_hard_fail_baseline_remains_invalid(self):
        result = self.evaluator._evaluate_baseline_status(
            scenario=dict(CONSTELLATION_2_NO_ATTACK_SCENARIO),
            terminal_metrics={"AverageEndingReward": 0.18, "PacketLossRate": 0.40},
            terminal_hard_failure=True,
            true_failure_v2=True,
        )

        self.assertEqual(result["baseline_status"], "invalid")
        self.assertFalse(result["baseline_valid"])
        self.assertEqual(result["baseline_profile"], "constellation_2")
        self.assertIn("constellation2_terminal_hard_failure", result["baseline_reason_codes"])


class InitialBaselineEarlyFailTests(unittest.TestCase):
    def setUp(self):
        self.simulation = ClosedLoopFailureSimulation.__new__(ClosedLoopFailureSimulation)

    def test_round_zero_invalid_no_attack_baseline_raises(self):
        invalid_record = {
            "test_id": 3,
            "scenario": dict(NO_ATTACK_SCENARIO),
            "baseline_status": "invalid",
            "terminal_average_ending_reward": 0.40,
            "terminal_packet_loss_rate": 0.35,
            "terminal_hard_failure": True,
            "baseline_reason_codes": ["terminal_hard_failure", "packet_loss_above_operable"],
        }

        with self.assertRaises(RuntimeError) as exc_info:
            self.simulation._validate_initial_baseline_gate(0, [invalid_record])

        message = str(exc_info.exception)
        self.assertIn("round_000", message)
        self.assertIn("\"test_id\": 3", message)
        self.assertIn("\"AverageEndingReward\": 0.4", message)

    def test_round_zero_operable_baseline_passes(self):
        operable_record = {
            "test_id": 1,
            "scenario": dict(NO_ATTACK_SCENARIO),
            "baseline_status": "operable",
            "terminal_average_ending_reward": 0.50,
            "terminal_packet_loss_rate": 0.20,
            "terminal_hard_failure": False,
            "baseline_reason_codes": ["reward_below_healthy"],
        }

        self.simulation._validate_initial_baseline_gate(0, [operable_record])

    def test_round_zero_constellation_two_fragile_baseline_passes(self):
        fragile_record = {
            "test_id": 7,
            "scenario": dict(CONSTELLATION_2_NO_ATTACK_SCENARIO),
            "baseline_status": "fragile",
            "terminal_average_ending_reward": 0.46,
            "terminal_packet_loss_rate": 0.17,
            "terminal_hard_failure": False,
            "baseline_reason_codes": ["constellation2_fragile_baseline"],
        }

        self.simulation._validate_initial_baseline_gate(0, [fragile_record])

    def test_non_initial_round_does_not_raise(self):
        invalid_record = {
            "test_id": 5,
            "scenario": dict(NO_ATTACK_SCENARIO),
            "baseline_status": "invalid",
            "terminal_average_ending_reward": 0.30,
            "terminal_packet_loss_rate": 0.40,
            "terminal_hard_failure": True,
            "baseline_reason_codes": ["terminal_hard_failure"],
        }

        self.simulation._validate_initial_baseline_gate(1, [invalid_record])

    def test_attack_scenario_is_ignored_by_round_zero_gate(self):
        attack_record = {
            "test_id": 6,
            "scenario": {**NO_ATTACK_SCENARIO, "RewardAttack_level": 2},
            "baseline_status": "invalid",
            "terminal_average_ending_reward": 0.10,
            "terminal_packet_loss_rate": 0.90,
            "terminal_hard_failure": True,
            "baseline_reason_codes": ["terminal_hard_failure"],
        }

        self.simulation._validate_initial_baseline_gate(0, [attack_record])


if __name__ == "__main__":
    unittest.main()
