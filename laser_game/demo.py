"""Simple command line demo for the laser game logic."""

from pathlib import Path

from .game import LaserGame, LevelLoader, SolutionValidator


def main() -> None:
    package_root = Path(__file__).resolve().parent
    level_loader = LevelLoader(package_root / "levels")
    solutions_root = package_root / "solutions"

    level_name = "level_intro"
    level = level_loader.load(level_name)

    validator = SolutionValidator(level_loader, solutions_root)
    solution = validator.load_solution(level_name)
    level = validator.apply_solution(level, solution)

    game = LaserGame(level)
    results = game.playthrough()

    print("=== Laser Game Demo ===")
    print(f"Level: {results['metadata']['name']} ({results['metadata']['difficulty']})")
    print("Target energy deliveries:")
    for target, energy in results["targets"].items():
        print(f"  {target}: {energy}")
    print(f"Beam segments simulated: {len(results['path'])}")


if __name__ == "__main__":
    main()
