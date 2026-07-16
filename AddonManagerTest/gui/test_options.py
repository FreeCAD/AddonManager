# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 FreeCAD Project Association
# SPDX-FileNotice: Part of the AddonManager.

################################################################################
#                                                                              #
#   This addon is free software: you can redistribute it and/or modify         #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   This addon is distributed in the hope that it will be useful,              #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with this addon. If not, see https://www.gnu.org/licenses    #
#                                                                              #
################################################################################

import unittest
from unittest.mock import patch


class MockParameters:
    """Stands in for FreeCAD's parameter store, which does not exist outside FreeCAD."""

    def __init__(self, custom_repositories: str = ""):
        self.parameters = {"CustomRepositories": custom_repositories}

    def GetString(self, name: str, default: str) -> str:
        return self.parameters.get(name, default)

    def SetString(self, name: str, value: str) -> None:
        self.parameters[name] = value


class TestCustomRepoDataModel(unittest.TestCase):
    """Tests for the storage of the custom repositories a user has configured. A repository may
    have no branch, which means its default branch, whatever the repository says that is."""

    def _model(self, custom_repositories: str = ""):
        self.parameters = MockParameters(custom_repositories)
        with patch("AddonManagerOptions.fci.FreeCAD") as mock_freecad:
            mock_freecad.ParamGet.return_value = self.parameters
            from AddonManagerOptions import CustomRepoDataModel

            return CustomRepoDataModel()

    def test_a_repository_with_a_branch_is_loaded(self):
        model = self._model("https://git.example.com/user/addon some-branch\n")

        self.assertEqual([["https://git.example.com/user/addon", "some-branch"]], model.model)

    def test_a_repository_with_no_branch_keeps_its_branch_empty(self):
        """The branch is not invented: an empty one means the repository's default branch, which is
        worked out from the repository itself when the addon list is built."""
        model = self._model("https://git.example.com/user/addon\n")

        self.assertEqual([["https://git.example.com/user/addon", ""]], model.model)

    def test_a_repository_with_no_branch_is_saved_without_one(self):
        model = self._model()
        model.model = [["https://git.example.com/user/addon", ""]]

        model.save_model()

        self.assertEqual(
            "https://git.example.com/user/addon\n", self.parameters.parameters["CustomRepositories"]
        )

    def test_a_repository_with_a_branch_is_saved_with_it(self):
        model = self._model()
        model.model = [["https://git.example.com/user/addon", "some-branch"]]

        model.save_model()

        self.assertEqual(
            "https://git.example.com/user/addon some-branch\n",
            self.parameters.parameters["CustomRepositories"],
        )

    def test_repositories_survive_a_round_trip(self):
        model = self._model()
        model.model = [
            ["https://git.example.com/user/with-branch", "some-branch"],
            ["https://git.example.com/user/without-branch", ""],
        ]

        model.save_model()
        model.load_model()

        self.assertEqual(
            [
                ["https://git.example.com/user/with-branch", "some-branch"],
                ["https://git.example.com/user/without-branch", ""],
            ],
            model.model,
        )


if __name__ == "__main__":
    unittest.main()
