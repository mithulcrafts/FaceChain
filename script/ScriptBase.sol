// SPDX-License-Identifier: MIT
pragma solidity ^0.8.25;

interface Vm {
    function startBroadcast() external;

    function startBroadcast(uint256 privateKey) external;

    function startBroadcast(address sender) external;

    function stopBroadcast() external;

    function envAddress(string calldata key) external returns (address value);

    function envBytes32(string calldata key) external returns (bytes32 value);

    function envUint(string calldata key) external returns (uint256 value);

    function envString(string calldata key) external returns (string memory value);
}

abstract contract ScriptBase {
    // forge-lint: disable-next-line(screaming-snake-case-const)
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
}
