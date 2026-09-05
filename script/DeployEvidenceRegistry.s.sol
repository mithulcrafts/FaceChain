// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

import {EvidenceRegistry} from "../src/EvidenceRegistry.sol";
import {ScriptBase} from "./ScriptBase.sol";

contract DeployEvidenceRegistry is ScriptBase {
    function run() external returns (address registry) {
        vm.startBroadcast();
        registry = address(new EvidenceRegistry());
        vm.stopBroadcast();
    }
}
