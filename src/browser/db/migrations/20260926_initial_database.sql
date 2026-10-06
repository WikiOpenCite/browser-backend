-- SPDX-FileCopyrightText: 2026 The University of St Andrews
-- SPDX-License-Identifier: GPL-3.0-or-later

CREATE TABLE `Migration` (
  `Name` varchar(64) UNIQUE PRIMARY KEY NOT NULL
);

CREATE TABLE `Institution` (
  `OpenAlexId` INT UNIQUE PRIMARY KEY NOT NULL,
  `Name` VARCHAR(512),
  `ROR` VARCHAR(9)
);

CREATE TABLE `Author` (
  `OpenAlexId` INT UNIQUE PRIMARY KEY NOT NULL,
  `Name` VARCHAR(512),
  `ORCID` VARCHAR(16)
);

CREATE TABLE `Work` (
  `OpenAlexId` INT UNIQUE PRIMARY KEY NOT NULL,
  `Title` VARCHAR(512),
  `PublicationDate` DATE,
  `Language` VARCHAR(3),
  `OAStatus` ENUM ('OA_CATEGORY_UNSPECIFIED', 'OA_CATEGORY_DIAMOND', 'OA_CATEGORY_GOLD', 'OA_CATEGORY_GREEN', 'OA_CATEGORY_HYBRID', 'OA_CATEGORY_BRONZE', 'OA_CATEGORY_CLOSED') DEFAULT 'OA_CATEGORY_UNSPECIFIED',
  `OA_Url` VARCHAR(1024),
  `DOI` VARCHAR(255),
  `ISBN` VARCHAR(13),
  `PMID` INT,
  `PMCID` INT,
  `ISSN` VARCHAR(8)
);

CREATE TABLE `WorkAuthors` (
  `AuthorId` INT NOT NULL,
  `WorkId` INT NOT NULL,
  PRIMARY KEY (`AuthorId`, `WorkId`)
);

CREATE TABLE `WorkInstitutions` (
  `InstitutionId` INT NOT NULL,
  `WorkId` INT NOT NULL,
  PRIMARY KEY (`InstitutionId`, `WorkId`)
);

CREATE TABLE `Revision` (
  `RevisionId` INT PRIMARY KEY NOT NULL,
  `ParentId` INT,
  `User` VARCHAR(255),
  `Timestamp` DATETIME
);

CREATE TABLE `Wiki` (
  `WikiId` VARCHAR(64) PRIMARY KEY NOT NULL
);

CREATE TABLE `Page` (
  `PageId` INT PRIMARY KEY NOT NULL,
  `PageTitle` VARCHAR(512),
  `Wiki` VARCHAR(64) NOT NULL
);

CREATE TABLE `Citation` (
  `CitationId` INT PRIMARY KEY NOT NULL AUTO_INCREMENT,
  `Page` INT NOT NULL,
  `RevisionAdded` INT NOT NULL,
  `RevisionRemoved` INT,
  `Work` INT
);

CREATE TABLE `URL` (
  `URLId` INT PRIMARY KEY NOT NULL AUTO_INCREMENT,
  `Citation` INT NOT NULL,
  `Type` ENUM ('URL_TYPE_UNSPECIFIED', 'URL_TYPE_DEFAULT', 'URL_TYPE_ARCHIVE') NOT NULL DEFAULT 'URL_TYPE_UNSPECIFIED',
  `URL` VARCHAR(1024) NOT NULL
);

CREATE INDEX `ix_work_title` ON `Work` (`Title`);

CREATE INDEX `ix_work_doi` ON `Work` (`DOI`);

ALTER TABLE `WorkAuthors` ADD FOREIGN KEY (`AuthorId`) REFERENCES `Author` (`OpenAlexId`);

ALTER TABLE `WorkAuthors` ADD FOREIGN KEY (`WorkId`) REFERENCES `Work` (`OpenAlexId`);

ALTER TABLE `WorkInstitutions` ADD FOREIGN KEY (`InstitutionId`) REFERENCES `Institution` (`OpenAlexId`);

ALTER TABLE `WorkInstitutions` ADD FOREIGN KEY (`WorkId`) REFERENCES `Work` (`OpenAlexId`);

ALTER TABLE `Page` ADD FOREIGN KEY (`Wiki`) REFERENCES `Wiki` (`WikiId`);

ALTER TABLE `Citation` ADD FOREIGN KEY (`Page`) REFERENCES `Page` (`PageId`);

ALTER TABLE `Citation` ADD FOREIGN KEY (`RevisionAdded`) REFERENCES `Revision` (`RevisionId`);

ALTER TABLE `Citation` ADD FOREIGN KEY (`RevisionRemoved`) REFERENCES `Revision` (`RevisionId`);

ALTER TABLE `Citation` ADD FOREIGN KEY (`Work`) REFERENCES `Work` (`OpenAlexId`);

ALTER TABLE `URL` ADD FOREIGN KEY (`Citation`) REFERENCES `Citation` (`CitationId`);